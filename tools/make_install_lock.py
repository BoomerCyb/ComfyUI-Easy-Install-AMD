"""Write helper/amd/install-lock.json from a verified installation.

Run after a fresh installation of the release candidate has passed testing:

    python tools/make_install_lock.py D:/path/to/ComfyUI-Easy-Install-AMD

It records the ComfyUI commit, each default node's commit (amd/nodes.json), and
the package versions setup installed (the receipt in amd/active-bundle.json,
written when setup finished, before any add-on). Only the standard library is used.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "helper/amd/install-lock.json"


def head(path: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("install", type=Path, help="a verified ComfyUI-Easy-Install-AMD installation")
    install = parser.parse_args().install.resolve()
    receipt = json.loads((install / "amd/active-bundle.json").read_text(encoding="utf-8"))
    manifest = json.loads((install / "amd/helper-manifest.json").read_text(encoding="utf-8"))
    nodes = json.loads((ROOT / "helper/amd/nodes.json").read_text(encoding="utf-8"))
    missing = [n["name"] for n in nodes if not (install / "ComfyUI/custom_nodes" / n["name"] / ".git").exists()]
    if missing:
        raise SystemExit("Not installed in that installation: " + ", ".join(missing))
    packages = {p["name"]: p["version"] for p in receipt["packages"]}
    lock = {
        "tested": {"date": date.today().isoformat(), "easy_install": manifest["version"],
                   "architecture": receipt["architecture"], **receipt["verified"]},
        "pip": packages.get("pip"),
        "comfyui": head(install / "ComfyUI"),
        "nodes": {n["name"]: head(install / "ComfyUI/custom_nodes" / n["name"]) for n in nodes},
        "packages": dict(sorted(packages.items(), key=lambda item: item[0].lower())),
    }
    LOCK.write_text(json.dumps(lock, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {LOCK.relative_to(ROOT)}: ComfyUI {lock['comfyui'][:12]}, {len(lock['nodes'])} nodes, "
          f"{len(lock['packages'])} packages (tested with {manifest['version']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
