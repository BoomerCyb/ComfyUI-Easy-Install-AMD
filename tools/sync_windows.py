"""Copy the installer files from this source checkout to a checkout of the Windows branch.

The Windows branch is what users get from the green Code button (clone or
Download ZIP), and the installer installs into that folder. It therefore holds
only the files a user needs; the source (helper/, tools/, docs/) stays on the
source branch. Run after merging a release into source:

    git worktree add ../ezi-windows Windows
    python tools/sync_windows.py ../ezi-windows
    (then commit in ../ezi-windows and open a pull request into Windows)

Only the standard library is used.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The release ZIP contents, plus .gitattributes so clones get CRLF batch files.
USER_FILES = ("ComfyUI-Easy-Install-AMD.bat", "Helper-CEI.zip", "README.md", "LICENSE")
WINDOWS_ONLY = (".gitattributes", ".git")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("windows_checkout", type=Path, help="a checkout of the Windows branch")
    target = parser.parse_args().windows_checkout.resolve()
    if target == ROOT or not (target / ".git").exists():
        raise SystemExit(f"{target} is not a separate checkout of the Windows branch.")
    if subprocess.run([sys.executable, str(ROOT / "tools/build_release.py"), "--check"]).returncode:
        raise SystemExit("Helper-CEI.zip is out of date; rebuild it on the source branch first.")
    for name in USER_FILES:
        shutil.copy2(ROOT / name, target / name)
        print("Copied", name)
    extra = sorted(p.name for p in target.iterdir() if p.name not in USER_FILES + WINDOWS_ONLY)
    if extra:
        print("Not user files; remove them from the Windows branch:", ", ".join(extra))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
