from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.executable).resolve().parent
    script = root / "Start-A5.ps1"
    log_dir = root / "logs"
    log_dir.mkdir(exist_ok=True)
    if not script.exists():
        (log_dir / "launcher-exe.log").write_text(f"Missing startup script: {script}\n", encoding="utf-8")
        return 1

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script),
        ],
        cwd=str(root),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
