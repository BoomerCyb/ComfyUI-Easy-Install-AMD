"""Build Helper-CEI.zip and the release ZIP from the helper/ source folder.

helper/ holds the installer's code (amd/, Add-Ons/, launchers, ...). Edit files
there, then run:

    python tools/build_release.py            # rebuild Helper-CEI.zip from helper/
    python tools/build_release.py --check    # fail if Helper-CEI.zip and helper/ differ
    python tools/build_release.py --release  # also write dist/ComfyUI-Easy-Install-AMD.zip

Helper-CEI.zip stays committed so source downloads of the repository keep
working; --check (run in CI) keeps it identical to helper/. Only the standard
library is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "helper"
HELPER_ZIP = ROOT / "Helper-CEI.zip"
RELEASE_ZIP = ROOT / "dist" / "ComfyUI-Easy-Install-AMD.zip"
RELEASE_DIR = "ComfyUI-Easy-Install-AMD"
# Generated into Helper-CEI.zip only (not kept in helper/): version and file hashes.
MANIFEST = "amd/helper-manifest.json"
RELEASE_FILES = ("ComfyUI-Easy-Install-AMD.bat", "Helper-CEI.zip", "README.md", "LICENSE")
# Fixed timestamp so rebuilding unchanged sources gives an identical ZIP.
TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def require_crlf(name: str, data: bytes) -> bytes:
    """cmd.exe can mis-handle labels in batch files that are not CRLF throughout."""
    if name.lower().endswith(".bat") and b"\n" in data.replace(b"\r\n", b""):
        raise SystemExit(f"{name} has LF-only line endings; batch files must use CRLF.")
    return data


def helper_version() -> str:
    """The release version, which the desktop app and the launcher must agree on."""
    versions = set()
    for name, pattern in (("ComfyUI-EZi.py", r'^APP_VERSION = "([^"]+)"'),
                          ("ComfyUI-EZi-Launcher.py", r"^VERSION = '([^']+)'")):
        text = (HELPER / "Add-Ons/Tools/Helper-CEI" / name).read_text(encoding="utf-8")
        match = re.search(pattern, text, re.M)
        if not match:
            raise SystemExit(f"No version found in {name}")
        versions.add(match.group(1))
    if len(versions) != 1:
        raise SystemExit(f"ComfyUI-EZi.py and ComfyUI-EZi-Launcher.py disagree on the version: {sorted(versions)}")
    return versions.pop()


def check_documentation() -> None:
    """The installer removes the root README and LICENSE only when they match these copies."""
    for name in ("README.md", "LICENSE"):
        if (ROOT / name).read_bytes() != (HELPER / "documentation" / name).read_bytes():
            raise SystemExit(f"{name} differs from helper/documentation/{name}; copy it there.")


def launcher_records(files: dict[str, bytes]) -> dict[str, dict]:
    """For each Start launcher: the hash of its text without the ComfyUI arguments, and the arguments.

    The updater uses them to carry a user's argument changes (toggles, folder settings) over.
    """
    sys.path.insert(0, str(HELPER / "amd"))
    sys.dont_write_bytecode = True
    import launcher_args
    records = {}
    for name, data in files.items():
        if "/" not in name and name.startswith("Start ComfyUI") and name.endswith(".bat"):
            parts = launcher_args.split(data.decode("utf-8"))
            if not parts:
                raise SystemExit(f"{name}: no single ComfyUI command line found")
            body, args = parts
            records[name] = {"body": hashlib.sha256(body.encode("utf-8")).hexdigest(), "args": args}
    return records


def helper_files() -> dict[str, bytes]:
    check_documentation()
    files = {}
    for path in sorted(HELPER.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            name = path.relative_to(HELPER).as_posix()
            files[name] = require_crlf(name, path.read_bytes())
    if not files:
        raise SystemExit(f"No files found in {HELPER}")
    # Lets "Update Easy-Install.bat" tell files the user edited from shipped ones.
    manifest = {"version": helper_version(),
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
                "launchers": launcher_records(files)}
    files[MANIFEST] = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode("ascii")
    return files


def write_zip(target: Path, entries: dict[str, bytes]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    temporary.replace(target)


def check() -> int:
    expected = helper_files()
    with zipfile.ZipFile(HELPER_ZIP) as archive:
        actual = {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    for label, names in (("missing from Helper-CEI.zip", missing),
                         ("in Helper-CEI.zip but not in helper/", extra),
                         ("different in Helper-CEI.zip", changed)):
        for name in names:
            print(f"{label}: {name}")
    if missing or extra or changed:
        print("Helper-CEI.zip is out of date. Run: python tools/build_release.py")
        return 1
    print(f"Helper-CEI.zip matches helper/ ({len(expected)} files).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify Helper-CEI.zip against helper/")
    parser.add_argument("--release", action="store_true", help="also build dist/ComfyUI-Easy-Install-AMD.zip")
    args = parser.parse_args()
    if args.check:
        return check()
    write_zip(HELPER_ZIP, helper_files())
    print(f"Wrote {HELPER_ZIP.name} from helper/.")
    if args.release:
        write_zip(RELEASE_ZIP, {f"{RELEASE_DIR}/{name}": require_crlf(name, (ROOT / name).read_bytes())
                                for name in RELEASE_FILES})
        print(f"Wrote {RELEASE_ZIP.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
