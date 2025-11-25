#!/usr/bin/env python3
"""
Simple web UI backend for analyze_reports.py
Features:
- Upload documents by department path (hierarchical storage under web_uploads/)
- Configure API key, models, temperature
- Run analysis and return output paths/logs
- Download output files
"""

from __future__ import annotations

import io
import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Callable, Optional
from queue import Queue
from threading import Thread

from flask import Flask, jsonify, request, send_from_directory, abort, stream_with_context
from werkzeug.utils import secure_filename

import analyze_reports

APP = Flask(__name__)

BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_ROOT = BASE_DIR / "up_load"
RUN_ROOT = BASE_DIR / "web_runs"
UPLOAD_ROOT.mkdir(exist_ok=True)
RUN_ROOT.mkdir(exist_ok=True)


def safe_join(root: Path, relative_path: str | Path) -> Path:
    """Join and ensure the path stays within root (prevent path traversal)."""
    root_resolved = root.resolve()
    full = (root_resolved / Path(relative_path)).resolve()
    try:
        full.relative_to(root_resolved)
    except ValueError:
        raise ValueError("Invalid path")
    return full


@APP.route("/upload", methods=["POST"])
def upload_files():
    dept = request.form.get("department", "").strip()
    target = UPLOAD_ROOT / dept if dept else UPLOAD_ROOT
    target.mkdir(parents=True, exist_ok=True)
    saved = []
    for file in request.files.getlist("files"):
        fname = secure_filename(file.filename)
        if not fname:
            continue
        dest = target / fname
        dest.parent.mkdir(parents=True, exist_ok=True)
        file.save(dest)
        saved.append(str(dest.relative_to(BASE_DIR)))
    return jsonify({"saved": saved, "upload_root": str(UPLOAD_ROOT.relative_to(BASE_DIR))})


def build_tree(root: Path) -> Dict[str, Any]:
    node = {"name": root.name, "path": root.relative_to(BASE_DIR).as_posix(), "type": "dir", "children": []}
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except FileNotFoundError:
        return node
    for entry in entries:
        if entry.is_dir():
            node["children"].append(build_tree(entry))
        else:
            node["children"].append(
                {
                    "name": entry.name,
                    "path": entry.relative_to(BASE_DIR).as_posix(),
                    "type": "file",
                    "size": entry.stat().st_size,
                }
            )
    return node


@APP.route("/tree", methods=["GET"])
def tree():
    return jsonify(build_tree(UPLOAD_ROOT))


@APP.route("/delete", methods=["POST"])
def delete_path():
    data = request.get_json(force=True)
    rel_path = data.get("path")
    if not rel_path:
        return jsonify({"error": "missing path"}), 400
    try:
        target = safe_join(UPLOAD_ROOT, rel_path)
    except ValueError:
        return jsonify({"error": "invalid path"}), 400
    if not target.exists():
        return jsonify({"error": "not found"}), 404
    try:
        if target.is_dir():
            import shutil

            shutil.rmtree(target)
        else:
            target.unlink()
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": str(exc)}), 500
    return jsonify({"deleted": rel_path})


@APP.route("/mkdir", methods=["POST"])
def make_dir():
    data = request.get_json(force=True)
    rel_path = data.get("path")
    if not rel_path:
        return jsonify({"error": "missing path"}), 400
    try:
        target = safe_join(UPLOAD_ROOT, rel_path)
        target.mkdir(parents=True, exist_ok=True)
    except ValueError:
        return jsonify({"error": "invalid path"}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": str(exc)}), 500
    return jsonify({"created": rel_path})


def run_analysis(payload: Dict[str, Any], progress_cb: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    input_dir = payload.get("input_dir") or UPLOAD_ROOT
    input_dir = safe_join(BASE_DIR, str(input_dir)) if not isinstance(input_dir, Path) else input_dir
    temperature = float(payload.get("temperature", 1.3))
    model = payload.get("model", os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    aggregate_model = payload.get("aggregate_model", os.getenv("DEEPSEEK_AGG_MODEL", "deepseek-reasoner"))
    api_key = payload.get("api_key")
    plan_prompt = payload.get("plan_prompt")
    max_tokens_individual = int(payload.get("max_tokens_individual", 1100))
    max_tokens_aggregate = int(payload.get("max_tokens_aggregate", 5000))

    # quick check: ensure there are files to process
    if not any(Path(input_dir).rglob("*")):
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": f"输入目录为空: {input_dir}",
            "run_dir": None,
            "individual": None,
            "organization": None,
        }

    run_name = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = RUN_ROOT / run_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # set API key for this run only
    env_backup = os.environ.get("DEEPSEEK_API_KEY")
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key

    argv = [
        "--input",
        str(input_dir),
        "--out-dir",
        str(out_dir),
        "--model",
        model,
        "--aggregate-model",
        aggregate_model,
        "--temperature",
        str(temperature),
        "--max-tokens-individual",
        str(max_tokens_individual),
        "--max-tokens-aggregate",
        str(max_tokens_aggregate),
    ]
    if plan_prompt:
        argv.extend(["--plan-prompt", str(plan_prompt)])

    log_chunks: list[str] = []

    def emit(text: str) -> None:
        if not text:
            return
        log_chunks.append(text)
        if progress_cb:
            progress_cb(text)

    class Writer:
        def write(self, s: str) -> int:  # type: ignore[override]
            emit(s)
            return len(s)

        def flush(self) -> None:
            return

    exit_code = 0
    try:
        if progress_cb:
            emit("[web] 开始执行分析任务...\n")
        with io.StringIO() as fake_stdin:
            with open(os.devnull, "r") as devnull:
                sys_stdin = sys.stdin
                sys.stdin = devnull  # avoid blocking
                try:
                    from contextlib import redirect_stdout, redirect_stderr

                    writer = Writer()
                    with redirect_stdout(writer), redirect_stderr(writer):
                        analyze_reports.main(argv)
                finally:
                    sys.stdin = sys_stdin
    except SystemExit as exc:
        exit_code = int(exc.code) if isinstance(exc.code, int) else 1
        if exc.code not in (0, None):
            emit(str(exc))
    except Exception as exc:  # pragma: no cover
        exit_code = 1
        emit(str(exc))
    finally:
        if env_backup is None:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        else:
            os.environ["DEEPSEEK_API_KEY"] = env_backup
    if progress_cb:
        emit(f"[web] 任务结束，退出码 {exit_code}\n")

    full_log = "".join(log_chunks)

    indiv = out_dir / "individual_summaries.json"
    org = out_dir / "organization_review.md"

    return {
        "exit_code": exit_code,
        "stdout": full_log,
        "stderr": "",
        "run_dir": str(out_dir.relative_to(BASE_DIR)),
        "individual": str(indiv.relative_to(BASE_DIR)) if indiv.exists() else None,
        "organization": str(org.relative_to(BASE_DIR)) if org.exists() else None,
    }


@APP.route("/run", methods=["POST"])
def run_job():
    data = request.get_json(force=True)
    try:
        result = run_analysis(data or {})
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": str(exc)}), 500
    return jsonify(result)


@APP.route("/run-stream", methods=["POST"])
def run_stream():
    data = request.get_json(force=True)
    q: Queue[Any] = Queue()

    def progress(chunk: str) -> None:
        for line in chunk.splitlines(True):
            q.put({"type": "log", "message": line})

    def worker() -> None:
        try:
            result = run_analysis(data or {}, progress_cb=progress)
            q.put({"type": "done", **result})
        except Exception as exc:  # pragma: no cover
            q.put({"type": "error", "message": str(exc)})
        finally:
            q.put(None)

    Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    resp = APP.response_class(stream_with_context(stream()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@APP.route("/download")
def download_file():
    rel_path = request.args.get("path")
    if not rel_path:
        abort(400, "missing path")
    rel = Path(rel_path)
    # only allow files under RUN_ROOT or UPLOAD_ROOT
    candidates = [RUN_ROOT, UPLOAD_ROOT]
    file_path = None
    for root in candidates:
        try:
            resolved = safe_join(root, rel)
        except ValueError:
            continue
        if resolved.exists():
            file_path = resolved
            break
    if file_path is None:
        abort(404)
    return send_from_directory(directory=file_path.parent, path=file_path.name, as_attachment=True)


@APP.route("/", methods=["GET"])
def index():
    return send_from_directory("frontend", "index.html")


@APP.route("/frontend/<path:filename>")
def frontend_assets(filename: str):
    return send_from_directory("frontend", filename)


if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=5000, debug=False)
