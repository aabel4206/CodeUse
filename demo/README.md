# 🧠 CodeUse Audit Tool — CLI Demo (Checkpoint)

This demo runs the full pipeline
**Executor → Adapter → Aggregator → Reporter**
without the web UI.
It launches a test page, performs a slow-motion audit, and writes results to `runs/<run_id>/`.

---

## 1️⃣ Setup

### Requirements

* **Python ≥ 3.10**
* **Pip** installed
* **Playwright** runtime (Chromium)
* `.env` file with your OpenRouter key

### Install dependencies

**Linux/macOS:**
```bash
python3 -m pip install -r requirements.txt
```

**Windows:**
```cmd
python -m pip install -r requirements.txt
```

If Playwright isn't installed yet:

**Linux/macOS:**
```bash
python3 -m playwright install chromium
```

**Windows:**
```cmd
python -m playwright install chromium
```

> 💡 **If `playwright` command not found:**
> Use `npx playwright install chromium` instead — this pulls Playwright via Node JS without touching your Python env.

---

## 2️⃣ Environment Variables

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=<your_key>
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```

---

## 3️⃣ Start the Test Page

From a new terminal:

**Linux/macOS:**
```bash
cd demo/site
python3 -m http.server 5173
```

**Windows:**
```cmd
cd demo\site
python -m http.server 5173
```

You can visit the page at
👉 `http://localhost:5173`

---

## 4️⃣ Run the Full Audit

From the project root:

**Linux/macOS:**
```bash
export PYTHONPATH="$(pwd)"

python3 demo/cli.py \
  --url http://localhost:5173 \
  --prompt-file demo/prompts/full_page_audit.json \
  --slow-ms 800
```

**Windows Command Prompt:**
```cmd
set PYTHONPATH=%CD%

python demo\cli.py --url http://localhost:5173 --prompt-file demo\prompts\full_page_audit.json --slow-ms 800
```

**Windows PowerShell:**
```powershell
$env:PYTHONPATH = (Get-Location).Path

python demo\cli.py --url http://localhost:5173 --prompt-file demo\prompts\full_page_audit.json --slow-ms 800
```

* `--url` → page to audit
* `--prompt-file` → Gemini-style JSON of actions
* `--slow-ms` → delay (ms) between Playwright steps for narration

### Follow-one-link demo

- The index page is in-spec and links to `page2.html`.
- By default the CLI follows the first same-origin link and audits the child page, surfacing hover spec failures, missing alt text, tiny click targets, overlays, and broken links.
- Disable link following with `--no-follow` if you only want to stay on the landing page.

---

## 5️⃣ Outputs

When complete, you’ll see a summary like:

```
=== DEMO SUMMARY ===
Run ID:        d230d34c
Result JSON:   runs/d230d34c/result.json
UI JSON:       runs/d230d34c/ui.json
Target URL:    http://localhost:5173/
CTA:           #btn1
Success:       False
Issue types:   {'hover_animation':1,'small_click_target':1,'console_error':1,'broken_link':1,'missing_alt':1}
```

Files are written to:

```
runs/<run_id>/result.json
runs/<run_id>/ui.json
```

---

## 6️⃣ Common Issues

| Error                                     | Fix                                             |
| ----------------------------------------- | ----------------------------------------------- |
| `ModuleNotFoundError: dotenv`             | `pip install python-dotenv`                     |
| `TypeError: 'str' object is not callable` | Update to latest branch (executor patch)        |
| `playwright: command not found`           | Run `npx playwright install chromium`           |
| Browser never opens                       | Re-run `python -m playwright install chromium` (Windows) or `python3 -m playwright install chromium` (Linux/macOS) |
| SyntaxWarning `\s`                        | Harmless; raw strings now used                  |

---

## 7️⃣ Re-run Quickly

To repeat a run with different speed:

**Linux/macOS:**
```bash
python3 demo/cli.py --url http://localhost:5173 --slow-ms 500
```

**Windows:**
```cmd
python demo\cli.py --url http://localhost:5173 --slow-ms 500
```

---

### ✅ That’s it!

You now have a fully working, **CLI-only demo** of the CodeUse Google Computer Use orchestration pipeline.
The next step for the UI team is to visualize `ui.json` in the static viewer.
