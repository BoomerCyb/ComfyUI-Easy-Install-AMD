"""Build the BoomerCyb nodes' native modules once for every Radeon architecture, as a release ZIP.

Run on a machine with the build tools (Visual Studio C++, the nodes' prerequisites),
using an installation of the release's default bundle:

    python tools/build_prebuilt.py D:/path/to/ComfyUI-Easy-Install-AMD --tag nodes-torch2.14.0-20261008

It installs/updates the BoomerCyb node group there with PYTORCH_ROCM_ARCH set to all
architectures, checks every build record lists them, packs the native modules into
dist/prebuilt/<asset>.zip and records it in helper/amd/prebuilt.json. Upload the ZIP
to the GitHub release named by --tag (not marked latest). Only the standard library
is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "helper/amd/prebuilt.json"
REPOSITORY = "BoomerCyb/ComfyUI-Easy-Install-AMD"
# Consumer Radeon architectures of AMD's Windows PyTorch bundles: RDNA1 to RDNA4.
ARCHITECTURES = ("gfx1010 gfx1011 gfx1012 gfx1030 gfx1031 gfx1032 gfx1033 gfx1034 gfx1035 gfx1036 "
                 "gfx1100 gfx1101 gfx1102 gfx1103 gfx1150 gfx1151 gfx1152 gfx1153 gfx1200 gfx1201").split()
SITE_FOLDERS = ("cumesh", "o_voxel", "trellis2")
WTIVO = "ComfyUI-WTiVo-WatertightVoxel-AMD"
TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def built_architectures(path: Path) -> set[str]:
    value = json.loads(path.read_text(encoding="utf-8")).get("architectures", "")
    return set(value if isinstance(value, list) else value.replace(",", ";").replace(" ", ";").split(";")) - {""}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("install", type=Path)
    parser.add_argument("--tag", required=True, help="GitHub release tag the ZIP will be uploaded to")
    parser.add_argument("--skip-build", action="store_true", help="pack the modules already built there")
    args = parser.parse_args()
    install = args.install.resolve()
    py = install / "python_embeded/python.exe"
    site = install / "python_embeded/Lib/site-packages"
    if not args.skip_build:
        env = dict(os.environ, PYTORCH_ROCM_ARCH=";".join(ARCHITECTURES), EZI_BUILD_FROM_SOURCE="1")
        subprocess.run([str(py), str(install / "amd/install_wtivo_group.py"), "boomercyb"],
                       cwd=install, env=env, check=True)
    probe = "import sys, torch, json; print(json.dumps([torch.__version__, torch.version.hip, '%d.%d' % sys.version_info[:2]]))"
    torch_version, hip, python = json.loads(subprocess.check_output([str(py), "-c", probe], text=True).splitlines()[-1])

    records = {"cumesh": site / "cumesh/_build_info.json", "o_voxel": site / "o_voxel/_build_info.json",
               "WTiVo": install / "ComfyUI/custom_nodes" / WTIVO / "build/hip-build-info.json"}
    for name, record in records.items():
        missing = set(ARCHITECTURES) - built_architectures(record)
        if missing:
            raise SystemExit(f"{name} was not built for: {' '.join(sorted(missing))}")
        if json.loads(record.read_text(encoding="utf-8")).get("torch") != torch_version:
            raise SystemExit(f"{name} was built for another PyTorch")

    report = json.loads((install / "amd/wtivo-boomercyb-installed.json").read_text(encoding="utf-8"))
    nodes = {name: subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=install / "ComfyUI/custom_nodes" / name,
                                           text=True).strip() for name in report["nodes"]}

    files = []
    for folder in SITE_FOLDERS:
        for path in sorted((site / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                files.append((path, "site-packages/" + path.relative_to(site).as_posix()))
    for dist in sorted(site.glob("cumesh-*.dist-info")):
        for path in sorted(dist.rglob("*")):
            if path.is_file():
                files.append((path, "site-packages/" + path.relative_to(site).as_posix()))
    build = install / "ComfyUI/custom_nodes" / WTIVO / "build"
    for path in sorted(build.iterdir()):
        if path.is_file():
            files.append((path, f"custom_nodes/{WTIVO}/build/{path.name}"))

    asset = f"boomercyb-nodes-torch{torch_version.replace('+', '-')}-py{python.replace('.', '')}.zip"
    target = ROOT / "dist/prebuilt" / asset
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in files:
            info = zipfile.ZipInfo(name, TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()

    entry = {"torch": torch_version, "hip": hip, "python": python, "architectures": list(ARCHITECTURES),
             "nodes": nodes, "asset": asset, "size": target.stat().st_size, "sha256": digest,
             "url": f"https://github.com/{REPOSITORY}/releases/download/{args.tag}/{asset}"}
    catalog = json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.is_file() else {"bundles": []}
    catalog["bundles"] = [b for b in catalog["bundles"]
                          if (b["torch"], b["python"]) != (torch_version, python)] + [entry]
    CATALOG.write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {target.relative_to(ROOT)} ({len(files)} files, {entry['size'] / 2**20:.1f} MB) and "
          f"{CATALOG.relative_to(ROOT)}. Upload it with:\n  gh release create {args.tag} {target} "
          f"--latest=false --title \"BoomerCyb nodes prebuilt for PyTorch {torch_version}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
