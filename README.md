<img width="1900" height="878" alt="image" src="https://github.com/user-attachments/assets/663a607f-f50e-4548-9c22-3d5a0d95c32f" /># Annual Report Batch Analyzer & Web UI

<img width="1900" height="878" alt="image" src="https://github.com/user-attachments/assets/51e17225-2844-4c38-8d93-773e33d8a122" />

## Overview
Batch process annual reports (txt/md/docx), extract structured per-person summaries via DeepSeek, then generate a consulting-style department/organization review. Prompts are fully customizable:
- Per-person: `prompts/individual/prompt.py`
- Aggregate: `prompts/aggregate/prompt.py`

## Architecture / Flow
- Core CLI: `analyze_reports.py`（加载 `.env`，扫描 `--input`，读取 txt/md/docx，调用 DeepSeek 逐篇提炼，归一化字段，输出 JSON & MD）。
- Prompt overrides: individual/aggregate prompt modules；导入失败自动回退到内置最小提示。
- Per-report handling: 标题关键词判定干部/员工；docx 轻量 XML 解析，txt/md 轮询常见编码读取。
- Normalization: 模型返回统一补齐字段（如 key_results/work_scope/methodologies/tags 等），缺失信息留空/空列表，写入源路径。
- Outputs: `analysis_output/per_report/<相对路径>.json`、`analysis_output/individual_summaries.json`、`analysis_output/organization_review.md`。
- Web UI: `web_app.py` + `frontend/` 支持上传/配置/运行/下载（日志目前仅终端可见）。

## Setup
1) Python 3.9+  
2) `pip install -r requirements.txt`  
3) 设置 `DEEPSEEK_API_KEY`（可放 `.env`；可选 `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`）  
4) 准备输入目录（示例）：
```
up_load/
  部门A/张三-干部.docx
  部门B/李四.md
```

## CLI Usage
一行：
```
python analyze_reports.py --input up_load --out-dir analysis_output --model deepseek-chat --aggregate-model deepseek-reasoner --temperature 1.3
```
PowerShell 多行：
```
python analyze_reports.py `
  --input up_load `
  --out-dir analysis_output `
  --model deepseek-chat `
  --aggregate-model deepseek-reasoner `
  --temperature 1.3
```
可选汇总附加提示：`--plan-prompt "2025 目标/项目提示"`

## Outputs & Schema
- Per-report JSON（镜像输入目录）：`analysis_output/per_report/<相对路径>.json`
- 汇总：`analysis_output/individual_summaries.json`（全部个体列表）、`analysis_output/organization_review.md`

单条 per-report JSON 字段（缺失时为空字符串/空列表）：
```json
{
  "name": "",
  "department": "",
  "role": "cadre|employee",
  "position": "",
  "title": "",
  "entry_date": "",
  "work_scope": "",
  "key_results": [],
  "capability_profile": [],
  "methodologies": [],
  "strengths": [],
  "improvements": [],
  "self_review": [],
  "issues": [],
  "suggestions": [],
  "workload": "",
  "support_to_departments": [],
  "risk_flags": [],
  "tags": [],
  "source_path": "up_load/部门/文件名.docx"
}
```
汇总 Markdown 头部示例：
```
# 年终总结评审
生成时间：2025-11-25T20:15:23
使用模型：个人提炼 deepseek-chat；汇总 deepseek-reasoner
采样温度：1.3
```

## Web UI
1) `python web_app.py`  
2) 打开 http://localhost:5000  
3) 上传 `up_load/` 下文件（支持子目录），配置 API Key/模型/温度/max_tokens，运行并下载输出（日志看终端）。

## Custom Prompts
编辑 `prompts/individual/prompt.py` 和 `prompts/aggregate/prompt.py` 自定义 system/user prompt；加载失败会回退最小提示。

## Notes / Known Issues
- 依赖 `openai>=1.3.0`。
- 终端编码若出现乱码，确保文件为 UTF-8 并在模型提示中声明语言。
- 作者注释：前端树状上传组件未显示、Web 日志仅终端可见，对运行无大碍。***
