# CodeUse Demo Instructions

## Serve the demo page

```bash
cd demo/site
python -m http.server 5173
```

The page will be available at <http://localhost:5173> and intentionally contains
hover, link, alt-text, and sizing issues for the auditor to detect.

## Run the slow-motion CLI against the live page

```bash
export PYTHONPATH="$(pwd)"
python demo/cli.py --url http://localhost:5173 --prompt-file demo/prompts/full_page_audit.json --slow-ms 800
```

## Use a saved executor blob

```bash
python demo/cli.py --executor-json examples/executor_out.json --prompt-file demo/prompts/hover_audit.json --slow-ms 800
```

## Outputs

- `runs/<run_id>/result.json` — canonical audit output for the orchestrator.
- `runs/<run_id>/ui.json` — condensed payload for the demo frontend.

The CLI prints a concise summary and echoes the Gemini CU prompt (if provided)
for narration during recorded demos. The backend continues to use the existing
Role C pipeline (adapter → aggregator → reporter → bridge).

## One-time setup on a fresh machine

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

