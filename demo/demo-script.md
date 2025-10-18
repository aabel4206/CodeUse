# CodeUse Demo Walkthrough

This scripted flow shows how the `tool.py` helper, executor artifacts, and reporter utilities stitch together to produce the final presentation assets.

## 1. Generate a synthetic run

```bash
python tool.py run --instruction "Fix the hero hover animation so it uses brand.primary."
```

What happens:

- A folder such as `runs/mock-20251018-191530/` is created with `result.json`, `summary.md`, and an `artifacts/` directory (screenshot + action log).
- A Markdown table of observations/errors is printed to the console, and aggregate views are refreshed (`runs/overview.md`, `runs/gallery.html`).

## 2. Inspect the raw run artifact

Open the newest folder in `runs/` to confirm the request/result metadata:

- `request` section → how the orchestrator (or mock) instructed the executor.
- `result` section → normalized status + timestamps returned by the executor.
- `artifacts` / `notes` → additional context the reporter can surface.

## 3. Re-run the report in isolation

```bash
python tool.py report
```

This command reads every `runs/<id>/result.json`, sorts them by `created_at`, prints the consolidated Markdown table, and regenerates `runs/overview.md` + `runs/gallery.html` (ready to paste into docs or slides).

## 4. Embed the gallery in a deck (optional)

To show the HTML gallery inside a slide:

1. Run `python -c "import pathlib, reporter; runs=reporter.load_runs(pathlib.Path('runs')); print(reporter.generate_report(runs).gallery_html)"`.
2. Copy the HTML output into a blank slide or an `iframe`.
3. Present the sleek, pre-styled cards during your demo.

## 5. Extend the scenario

- Adjust the mock payload inside `tool.py` to mirror your live tooling (different commands, durations, or artifact types).
- Drop additional JSON fixtures into `runs/` to highlight failures, timeouts, or flaky retries.
- Update `reporter/gallery.py` with custom styling that reflects your brand.

Once you are happy with the flow, keep this file nearby as your presenter notes.
