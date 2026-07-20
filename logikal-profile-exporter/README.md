# Logikal Profile Export Automation

Python tool that drives the Logikal CAD desktop UI (via Windows UI
Automation / `pywinauto`) to batch-export every Profile of a chosen
Manufacturer + System as an individual DXF file, named by Article
Number — with resume, retry, validation, and a CSV manifest.

> **Status:** implementation scaffold matching the full technical spec
> (architecture, resume/retry, manifest, validators, tests). The pieces
> that touch the real Logikal window (`src/logikal_app.py`,
> `src/profile_browser.py`, `src/drawing_exporter.py`, `src/dialogs.py`,
> `selectors/*.json`) are wired to the exact control-priority strategy
> in the spec (UIA controls → keyboard nav → coordinates → image match)
> but the **selector values themselves are placeholders** and must be
> confirmed against your real Logikal install in Phase 1 (UI Discovery)
> before running a real export — see below.

## 1. Requirements

- Windows 10/11 with Logikal installed and runnable by the same
  Windows account that runs this tool.
- Python 3.11 or 3.12, in a dedicated virtual environment.
- `Inspect.exe` (Windows SDK) or Accessibility Insights, for Phase 1.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`ezdxf`, `pydantic`, `rich`, `pywinauto`, `pywin32`, and `psutil` are
required. `pyautogui` / `opencv-python` are optional fallbacks for the
rare case where a control genuinely can't be reached via UIA or
keyboard (see risk table in the spec) — install them only if Phase 1
shows you need them.

## 2. Configure

```bash
copy config.example.json config.json
```

Edit `config.json`:

```json
{
  "logikal_executable": "C:\\Program Files\\Orgadata\\Logikal\\Logikal.exe",
  "manufacturer": "Schueco",
  "system": "FWS 50 SG",
  "export_root": "D:\\LogikalExports",
  "language": "en",
  "backend": "uia",
  "max_retries": 3,
  "dialog_timeout_seconds": 20,
  "file_timeout_seconds": 45,
  "skip_valid_existing_files": true,
  "validate_with_ezdxf": true
}
```

Manufacturer/System changes never require touching code — the tool
reads them from this file.

## 3. Phase 1 — UI Discovery (do this first, once per Logikal version)

1. Open Logikal manually, navigate to **Add Profile**, and record a
   short video of a single manual export end-to-end.
2. Run `Inspect.exe` (or Accessibility Insights) over each control used
   in that video: main window, Add Profile, Manufacturer, System,
   Article List, OK, Export Drawing, Save As.
3. With Logikal still open on that window, run:

   ```bash
   python scripts/discover_ui.py
   ```

   This saves a full control-identifier dump to `artifacts/`.
4. Update `selectors/en.json` (or `de.json`) with the real
   `AutomationId` / `ControlType` / titles / menu paths / keyboard
   shortcuts you found. The placeholder values shipped in this repo
   are best-guess defaults and are very likely to need correction —
   the risk table in the spec (list not exposed as UIA items, language
   differences, version drift) exists specifically for this step.

## 4. Run

```bash
python app.py --config config.json
```

Expected summary output:

```
Manufacturer : Schueco
System       : FWS 50 SG
Total        : 128
Exported     : 116
Skipped      : 10
Failed       : 2
Output       : D:\LogikalExports\Schueco\FWS_50_SG
```

Set `"connect_only": true` in `config.json` to just verify the tool can
connect to Logikal's main window without running any export — useful
right after finishing Phase 1.

Set `"article_limit": 10` while validating Phase 2/3 (single profile,
then first 10) before trusting a full-series run, per the spec's
recommended start order.

## 5. What gets produced

```
D:\LogikalExports\Schueco\FWS_50_SG\
├── 123456.dxf
├── 123457.dxf
├── export_manifest.csv     # append-only, one row per attempt
├── progress.json           # fast-checkpoint summary
├── export_errors.log       # traceback + active window per failed attempt
└── screenshots/            # captured on final failure of an article
```

`export_manifest.csv` is the source of truth for resume: on restart,
the tool re-checks every article that already has a terminal row
(Exported/Skipped) against the file that's actually on disk before
trusting it, rather than only looking at `progress.json`'s last
article.

## 6. Resume & retry behavior

- Interrupting the tool (Ctrl+C, Logikal crash, machine restart) is
  safe. Re-running `python app.py --config config.json` continues from
  where it left off; it does not restart the whole system.
- A valid, already-exported DXF is skipped (not re-exported) — recorded
  as `Skipped` in the manifest.
- Each article gets up to `max_retries` attempts. Before each retry,
  any stray popup is closed and the tool re-verifies the connection to
  Logikal.
- A single article that keeps failing is recorded as `Failed` and the
  run continues with the next article — it does not abort the whole
  series. The only thing that stops the whole run is losing the
  connection to Logikal entirely.

## 7. Testing

```bash
pytest
```

Runs the UI-independent test suite (config validation, resume state,
filename sanitization, DXF validation) — no Windows or Logikal
required, and safe to run in CI. UI-automation code
(`logikal_app.py`, `profile_browser.py`, `drawing_exporter.py`,
`dialogs.py`) is intentionally excluded from this suite; validate that
part manually against a real Logikal window per the checklist in the
spec's "خطة الاختبار" section (single profile → 10 profiles → full
series → interrupted-then-resumed run → run-twice-produces-identical-
result).

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Config file not found` | Wrong `--config` path | Check the path passed to `--config` |
| `Config validation failed` | Missing/blank field in `config.json`, or `backend`/`language` value not recognized | Compare against `config.example.json` |
| `No selectors file for language 'xx'` | `language` in config has no matching `selectors/xx.json` | Add the file or fix `language` |
| `Could not connect to Logikal main window` | Logikal not running, wrong `logikal_executable` path, or `title_re` in `selectors/en.json` doesn't match your Logikal version's window title | Start Logikal manually first and confirm the title in Task Manager / Inspect.exe |
| Article list comes back empty, tool falls back to keyboard navigation | The Article list isn't exposed as enumerable UIA child items | Expected on some Logikal versions — confirm `iter_articles_by_keyboard` reads the right "currently selected article" field for your version (Phase 1) |
| Files failing `validate_dxf` immediately after export | `wait_for_file_size_stable` timeout too short for large profiles, or DXF marker check needs adjusting for your Logikal DXF variant | Raise `file_timeout_seconds`; inspect one exported file by hand |
| Same article keeps getting `Failed` after every retry | A genuine UI mismatch (wrong selector) rather than a transient timing issue | Check `export_errors.log` and the matching screenshot in `screenshots/` |

## 9. Project layout

```
logikal-profile-exporter/
├── app.py                  # CLI entrypoint
├── config.example.json
├── requirements.txt
├── src/
│   ├── config.py            # load/validate config.json
│   ├── logikal_app.py       # connect/launch, main window handle
│   ├── profile_browser.py   # Add Profile, Manufacturer/System, Article list
│   ├── drawing_exporter.py  # add-to-drawing, export DXF, clear drawing
│   ├── dialogs.py           # Save As / Overwrite / unexpected popups
│   ├── automation.py        # LogikalExporter facade + export loop + series runner
│   ├── state_store.py       # progress.json (atomic writes)
│   ├── manifest.py          # export_manifest.csv
│   ├── validators.py        # DXF validation
│   ├── errors.py            # exception hierarchy
│   └── utils.py             # filename sanitizing, file-stability polling
├── selectors/
│   ├── en.json              # placeholder — confirm in Phase 1
│   └── de.json              # placeholder — confirm in Phase 1
├── scripts/
│   └── discover_ui.py       # Phase 1 UI Discovery dump
├── tests/                   # UI-independent unit tests (pytest)
├── logs/
└── exports/                 # created per manufacturer/system at runtime
```

## 10. Out of scope (v1)

Per the spec: reverse-engineering Logikal's internal database, bypassing
dongle/license protection, redistributing manufacturer libraries, STEP
or 3D geometry export, and a standalone GUI/EXE — all deferred until a
single profile, then 10 profiles, then a full series export succeed
reliably twice in a row.
