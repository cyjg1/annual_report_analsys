# Annual Report Batch Analyzer & Web UI

## Overview
This tool batch-processes annual reports (txt/md/docx), extracts structured per-person summaries via DeepSeek, and generates a consulting-style department/organization review. It supports custom prompts:
- Per-person: `prompts/individual/prompt.py`
- Aggregate: `prompts/aggregate/prompt.py`

## Setup
1) Python 3.9+  
2) Install deps: `pip install -r requirements.txt`  
3) Set env var `DEEPSEEK_API_KEY` (optional: `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`). You can place them in `.env` (see `.env.example`).
4) Prepare input dir (recommended structure):
```
up_load/
  部门A/张三-干部.docx
  部门B/李四.md
```
Supported file types: `txt`, `md`, `docx`.

## CLI Usage
Basic:
```
python analyze_reports.py --input uploads --out-dir analysis_output
```
Optional model/temperature:
```
python analyze_reports.py \
  --input reports --out-dir analysis_output \
  --model deepseek-chat --aggregate-model deepseek-reasoner \
  --temperature 1.3
```
Optional extra prompt for aggregate: `--plan-prompt "2025 目标/项目提示"`  
Outputs:
- `analysis_output/individual_summaries.json`
- `analysis_output/organization_review.md`
- Per-file JSON under `analysis_output/per_report/` (mirrors input structure)

## Web UI
1) Run: `python web_app.py`
2) Open: http://localhost:5000
3) Upload files to `up_load/` (supports nested folders), configure API Key/model/temperature/max_tokens, run, stream logs, and download outputs.
Outputs per run are stored under `web_runs/run-*/` with individual/organization files.

## Custom Prompts
- Edit `prompts/individual/prompt.py` and `prompts/aggregate/prompt.py` to fully control system/user prompts. If loading fails, the app falls back to a minimal prompt (system + raw content).

## Notes
- Requires `openai>=1.3.0`.
- If you see garbled output, ensure your prompt files are saved in UTF-8 and models are instructed to respond in the desired language.


作者注释：这个代码有两个bug，vibe coding一直修复不了，一个是我本来想做个前端上传，树状结构的上传，一直显示不出来，另一个就是日志完全打不出来，只有本地跑在终端可以看到，但好像不影响运行，就这样吧
