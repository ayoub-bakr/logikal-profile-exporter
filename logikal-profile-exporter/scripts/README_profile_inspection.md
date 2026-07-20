# LogiKal Profile Page Inspection

`inspect_profile_page.py` reads process, window, control, accessibility,
selection, and UI Automation pattern metadata from an already-open LogiKal
Profile Data page. It does not perform UI actions.

## Safety

The inspector does not click, type, change focus, select rows, invoke controls,
scroll, move windows, close dialogs, or export files. Before process inspection,
it parses its own source and refuses to run if a prohibited state-changing call
exists outside comments or string literals.

The utility identifies candidate processes from the executable name/path, not
from a broad window-title match. A browser whose title contains "Logikal" is not
accepted as a LogiKal process.

## Usage

1. Open LogiKal manually.
2. Navigate manually to the Profile Data page shown in the screenshot.
3. Leave profile `2256` selected.
4. Do not interact with the computer while the inspector is running.
5. Find the LogiKal PID by running:

   ```powershell
   python scripts/inspect_profile_page.py
   ```

6. If more than one LogiKal process is listed, run the inspector with the
   desired PID:

   ```powershell
   python scripts/inspect_profile_page.py --pid <PID>
   ```

7. Send the generated artifact folder for analysis.

Artifacts are written to:

```text
artifacts/profile_page_inspection_<timestamp>/
```

The folder contains:

- `process_windows.txt`
- `uia_control_tree.txt`
- `win32_control_tree.txt`
- `candidate_profile_lists.txt`
- `profile_items.json`
- `summary.json`
- `errors.txt`

## Dependencies

Install the project dependencies from `requirements.txt`. The inspector needs
`psutil`, `pywinauto`, and the Windows `pywin32` modules used by pywinauto.

```powershell
pip install -r requirements.txt
```

If `win32gui` is unavailable after that installation, install `pywin32`
explicitly:

```powershell
pip install pywin32
```
