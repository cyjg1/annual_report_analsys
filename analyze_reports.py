#!/usr/bin/env python3
"""
Batch process annual reports, call DeepSeek API to extract structured takeaways,
then produce department/company evaluations and a consulting-style summary.
Supports custom prompts via prompts/individual/prompt.py and prompts/aggregate/prompt.py.
Requires DEEPSEEK_API_KEY in env (optional DEEPSEEK_BASE_URL/DEEPSEEK_MODEL).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Callable, Optional

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - prompt user to install
    raise SystemExit("Missing dependency openai, install via: pip install openai") from exc


ALLOWED_SUFFIXES = {".txt", ".md", ".docx"}
MANAGER_HINTS = ("干部", "领导", "经理", "主管", "总监", "部长", "书记", "主任", "处长", "科长")
INDUSTRY_CONTEXT = (
    "部门聚焦钢铁行业解决方案交付，场景涵盖生产、质量、计划、物流、成本、ERP/产品运营等。"
    "研发包含前端与后端开发；产品为产品经理；模型算法室负责算法赋能；"
    "质量做钢厂质量分析与质量设计；物流做钢厂物流功能；产品运营室类似 ERP；"
    "计划做钢厂生产计划；管理层为部门领导与管控。"
)
# 部门关键词 -> 提示词偏好
DEPARTMENT_PROMPT_HINTS = [
    (("研发", "技术", "工程", "开发"), "研发（前端/后端）：关注架构/核心模块、稳定性/缺陷率、性能指标、交付节奏、复用与技术债务。"),
    (("产品", "产品经理"), "产品：关注需求测评、产品路线、共性能力沉淀、业务匹配度、交付与迭代节奏。"),
    (("模型", "算法"), "模型算法：关注算法赋能、模型效果/覆盖、数据质量、算力成本、上线与迭代节奏。"),
    (("质量", "质检", "测试"), "质量：关注缺陷发现率/漏检率、质量门禁、回归效率、工艺质量设计、风险预警。"),
    (("物流", "供应链", "仓储"), "物流：关注交付准确率、响应时效、库存/成本效率、流程优化与数字化。"),
    (("产品运营", "运营", "ERP"), "产品运营/ERP：关注流程覆盖、上线与运维、用户采用度、效率/成本改进。"),
    (("计划", "PMO", "项目管理"), "计划/PMO：关注生产计划/资源调配、里程碑兑现、关键路径、风险管控与协同。"),
    (("成本", "财务", "绩效"), "成本/绩效：关注成本节约、ROI、效率提升、财务合规、绩效改进。"),
    (("管控", "综合管理", "外委", "管理层"), "管控/管理：关注流程制度、供应商/外协管理、风险与合规、资源统筹、组织保障。"),
]


@dataclass
class Report:
    path: Path
    department: str
    title: str
    role: str
    content: str


def read_text_file(path: Path) -> str:
    """Try common encodings to read a text/markdown file."""
    for enc in ("utf-8", "utf-8-sig", "gbk", "cp936"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="ignore")


def read_docx_file(path: Path) -> str:
    """Lightweight docx parser to extract text from w:t tags."""
    texts: List[str] = []
    with zipfile.ZipFile(path) as zf:
        namelist = [name for name in zf.namelist() if name.startswith("word/") and name.endswith(".xml")]
        for name in namelist:
            if not any(key in name for key in ("document", "header", "footer")):
                continue
            xml_bytes = zf.read(name)
            root = ET.fromstring(xml_bytes)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for node in root.iter(ns + "t"):
                if node.text:
                    texts.append(node.text)
    return "\n".join(texts)


def load_content(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return read_text_file(path)
    if suffix == ".docx":
        try:
            return read_docx_file(path)
        except zipfile.BadZipFile:
            print(f"[警告] {path} 不是有效的 docx，尝试按文本读取")
            return read_text_file(path)
    raise ValueError(f"不支持的文件类型: {path.suffix}")


def load_env_from_file(file_path: Path) -> None:
    """Load key=value lines from a .env file into os.environ if not set."""
    if not file_path.exists():
        return
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def detect_role(title: str) -> str:
    return "cadre" if any(key in title for key in MANAGER_HINTS) else "employee"


def department_focus(department: str) -> str:
    dept_lower = department.lower()
    for keywords, hint in DEPARTMENT_PROMPT_HINTS:
        if any(k.lower() in dept_lower for k in keywords):
            return hint
    return "关注年度成果、工作量、优势、改进点、跨部门支撑与风险。"


def load_prompt_builder(module_name: str, func_name: str = "build_prompt") -> Optional[Callable[..., str]]:
    """Dynamically load a prompt builder from module.func if present; return None on failure."""
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.loader is None:
        parts = module_name.split(".")
        rel_path = Path(*parts)
        if not rel_path.suffix:
            rel_path = rel_path.with_suffix(".py")
        if rel_path.exists():
            spec = importlib.util.spec_from_file_location(module_name, rel_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
    except Exception:
        return None
    func = getattr(module, func_name, None)
    if callable(func):
        return func  # type: ignore[return-value]
    return None


def collect_reports(root: Path) -> List[Report]:
    reports: List[Report] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        relative = file_path.relative_to(root)
        department = relative.parts[0] if len(relative.parts) > 1 else "未分类"
        title = file_path.stem
        role = detect_role(title)
        content = load_content(file_path)
        reports.append(Report(path=file_path, department=department, title=title, role=role, content=content))
    return reports


def create_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("请先在环境变量中设置 DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return OpenAI(api_key=api_key, base_url=base_url)


def summarize_individual(
    client: OpenAI, model: str, report: Report, temperature: float, max_tokens: int
) -> Dict[str, Any]:
    """Call DeepSeek to produce a structured summary for one report."""
    dept_hint = department_focus(report.department)
    sys_prompt = (
        "You are an HR/Org design expert. Extract concise, decision-grade facts from the annual report. "
        "Respond ONLY with the required JSON object in Chinese, no extra text."
    )
    sys_prompt_builder = load_prompt_builder("prompts.individual.prompt", "build_system_prompt")
    if sys_prompt_builder:
        try:
            sys_prompt = sys_prompt_builder({"industry_context": INDUSTRY_CONTEXT, "department_focus": dept_hint})
        except Exception:
            pass
    prompt_builder = load_prompt_builder("prompts.individual.prompt")
    if prompt_builder:
        try:
            user_prompt = prompt_builder(
                {
                    "industry_context": INDUSTRY_CONTEXT,
                    "department_focus": dept_hint,
                    "report": report,
                    "raw_content": report.content,
                }
            )
        except Exception:
            user_prompt = report.content
    else:
        user_prompt = report.content
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        raise RuntimeError(f"调用模型失败: {exc}") from exc
    content = completion.choices[0].message.content if completion.choices else None
    if not content:
        raise RuntimeError("模型未返回内容")
    try:
        data = json.loads(content)
    except Exception:
        cleaned = content.strip()
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(cleaned)
        except Exception as exc:
            raise RuntimeError(f"无法解析模型返回的 JSON: {exc}; content={content}") from exc
    data["source_path"] = str(report.path)
    if "name" not in data or not data["name"]:
        data["name"] = report.title
    if "department" not in data or not data["department"]:
        data["department"] = report.department
    if "role" not in data or data["role"] not in {"cadre", "employee"}:
        data["role"] = report.role
    if "workload" not in data or not data["workload"]:
        data["workload"] = "未提及/估计"
    return data


def build_aggregate_prompt(
    people: Iterable[Dict[str, Any]],
    extra_prompt: str | None,
) -> str:
    compact: List[Dict[str, Any]] = []
    for person in people:
        compact.append(
            {
                "name": person.get("name"),
                "department": person.get("department"),
                "role": person.get("role"),
                "position": person.get("position"),
                "title": person.get("title"),
                "entry_date": person.get("entry_date"),
                "key_results": person.get("key_results", []),
                "strengths": person.get("strengths", []),
                "improvements": person.get("improvements", []),
                "self_review": person.get("self_review", []),
                "issues": person.get("issues", []),
                "suggestions": person.get("suggestions", []),
                "workload": person.get("workload"),
                "support_to_departments": person.get("support_to_departments", []),
                "risk_flags": person.get("risk_flags", []),
                "error": person.get("error"),
            }
        )
    people_json = json.dumps(compact, ensure_ascii=False, indent=2)
    extra = extra_prompt.strip() if extra_prompt else ""
    prompt_builder = load_prompt_builder("prompts.aggregate.prompt")
    if prompt_builder:
        try:
            return prompt_builder({"people": compact, "industry_context": INDUSTRY_CONTEXT})
        except Exception:
            pass
    return (
        f"Industry background: {INDUSTRY_CONTEXT}\n\n"
        f"Structured individual summaries:\n{people_json}\n\n"
        f"Additional context: {extra or 'None'}\n"
        f"Please generate the organization report per the system prompt requirements."
    )


def aggregate_review(
    client: OpenAI,
    model: str,
    people: List[Dict[str, Any]],
    temperature: float,
    extra_prompt: str | None,
    max_tokens: int,
) -> str:
    user_prompt = build_aggregate_prompt(people, extra_prompt)
    sys_prompt = "You are an organizational strategy consultant focusing on steel-industry solutions. Respond in Chinese with concise, actionable analysis."
    sys_prompt_builder = load_prompt_builder("prompts.aggregate.prompt", "build_system_prompt")
    if sys_prompt_builder:
        try:
            sys_prompt = sys_prompt_builder({"industry_context": INDUSTRY_CONTEXT})
        except Exception:
            pass
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        raise RuntimeError(f"调用模型失败: {exc}") from exc
    content = completion.choices[0].message.content if completion.choices else None
    if not content:
        raise RuntimeError("模型未返回内容")
    return content.strip()


def make_failure_record(report: Report, error: str) -> Dict[str, Any]:
    """Build a placeholder record when summarization fails."""
    return {
        "name": report.title,
        "department": report.department,
        "role": report.role,
        "position": "",
        "title": "",
        "entry_date": "",
        "key_results": [],
        "strengths": [],
        "improvements": [],
        "self_review": [],
        "issues": [],
        "suggestions": [],
        "workload": "提炼失败（估计）",
        "support_to_departments": [],
        "risk_flags": [],
        "source_path": str(report.path),
        "error": error,
    }


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="对多个年终总结生成个人/部门/公司评价（DeepSeek 驱动）")
    parser.add_argument("--input", required=True, type=Path, help="存放各部门年终总结的根目录")
    parser.add_argument("--out-dir", default=Path("analysis_output"), type=Path, help="输出结果目录")
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), help="个人提炼模型")
    parser.add_argument(
        "--aggregate-model",
        default=os.getenv("DEEPSEEK_AGG_MODEL", "deepseek-reasoner"),
        help="最终汇总使用的模型（默认 deepseek-reasoner）",
    )
    parser.add_argument(
        "--temperature",
        default=1.3,
        type=float,
        help="采样温度，个人提炼与最终汇总共用（默认 1.3）",
    )
    parser.add_argument(
        "--max-tokens-individual",
        default=4000,
        type=int,
        help="个人提炼阶段的 max_tokens（默认 4000，可在 4000-8000 调整）",
    )
    parser.add_argument(
        "--max-tokens-aggregate",
        default=32000,
        type=int,
        help="汇总阶段的 max_tokens（默认 32000，可在 32000-64000 调整）",
    )
    parser.add_argument("--env-file", default=Path(".env"), type=Path, help="包含 DEEPSEEK_API_KEY 的 .env 路径")
    parser.add_argument(
        "--plan-prompt",
        default=None,
        type=str,
        help="年初计划/指标等额外提示内容（直接文本，追加到汇总提示中）",
    )
    args = parser.parse_args(argv)

    load_env_from_file(args.env_file)

    if not args.input.exists():
        raise SystemExit(f"输入目录不存在: {args.input}")

    extra_prompt = args.plan_prompt

    client = create_client()
    reports = collect_reports(args.input)
    if not reports:
        raise SystemExit("未找到可处理的文件，请确认目录下包含 txt/md/docx 文件。")

    print(f"[信息] 发现 {len(reports)} 篇总结，开始逐篇提炼...")
    per_report_dir = args.out_dir / "per_report"
    per_report_dir.mkdir(parents=True, exist_ok=True)
    people: List[Dict[str, Any]] = []
    for idx, report in enumerate(reports, start=1):
        print(f"[{idx}/{len(reports)}] 处理 {report.path} ...")
        try:
            summary = summarize_individual(
                client, args.model, report, args.temperature, args.max_tokens_individual
            )
            people.append(summary)
            rel_json = report.path.relative_to(args.input).with_suffix(".json")
            dest = per_report_dir / rel_json
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"[错误] 提炼失败: {report.path} -> {exc}")
            fail = make_failure_record(report, str(exc))
            people.append(fail)
            rel_json = report.path.relative_to(args.input).with_suffix(".json")
            dest = per_report_dir / rel_json
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(fail, ensure_ascii=False, indent=2), encoding="utf-8")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    people_path = args.out_dir / "individual_summaries.json"
    people_path.write_text(json.dumps(people, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[完成] 已写入个人提炼结果: {people_path}")

    print("[信息] 开始生成部门与整体评价 ...")
    try:
        aggregate_markdown = aggregate_review(
            client,
            args.aggregate_model,
            people,
            args.temperature,
            extra_prompt,
            args.max_tokens_aggregate,
        )
        agg_error = None
    except Exception as exc:
        agg_error = str(exc)
        aggregate_markdown = f"生成失败：{agg_error}"
        print(f"[错误] 汇总失败: {agg_error}")

    report_path = args.out_dir / "organization_review.md"
    header = (
        f"# 年终总结评审\n\n"
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}\n"
        f"使用模型：个人提炼={args.model}；汇总={args.aggregate_model}\n"
        f"采样温度：{args.temperature}\n\n"
    )
    report_path.write_text(header + aggregate_markdown + "\n", encoding="utf-8")
    if agg_error:
        raise SystemExit("汇总失败，详见上方日志")
    print(f"[完成] 已写入综合报告: {report_path}")


if __name__ == "__main__":
    main()
