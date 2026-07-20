"""Phase 1: UI Discovery.

Connects to an already-running Logikal instance and dumps
print_control_identifiers() to artifacts/ so the tree can be reviewed
offline and used to fill in selectors/en.json (or de.json).

Run this manually, with Logikal already open on the Add Profile
window, before writing/trusting any automation code:

    python scripts/discover_ui.py --window-title-re ".*Logikal.*"
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from pywinauto import Application


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump Logikal UI control identifiers")
    parser.add_argument("--window-title-re", default=".*Logikal.*")
    parser.add_argument("--backend", default="uia", choices=["uia", "win32"])
    parser.add_argument("--out-dir", default="artifacts")
    args = parser.parse_args()

    app = Application(backend=args.backend).connect(
        title_re=args.window_title_re, timeout=20
    )
    window = app.window(title_re=args.window_title_re)
    window.wait("visible enabled ready", timeout=20)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"control_identifiers_{stamp}.txt"

    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        window.print_control_identifiers()

    out_path.write_text(buf.getvalue(), encoding="utf-8")
    print(f"Saved control identifiers to {out_path}")
    print("Open this file, locate each control from the discovery table in "
          "the spec (Manufacturer, System, Article List, OK, Export Drawing, "
          "Save As), and copy AutomationId/ControlType/Name into selectors/*.json.")


if __name__ == "__main__":
    main()
