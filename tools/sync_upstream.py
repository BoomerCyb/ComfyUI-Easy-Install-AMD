"""Merge a new upstream ComfyUI-Easy-Install release into helper/.

Upstream ships its code inside Helper-CEI.zip, so git cannot merge it
directly. This script downloads upstream's Helper-CEI.zip for the release we
last synced to (tools/upstream.json) and for the new one, and three-way merges
upstream's changes into helper/, file by file. Run it on a new branch:

    git switch -c sync/upstream-<tag> source
    python tools/sync_upstream.py              # latest upstream release
    python tools/sync_upstream.py --to 3.21.0  # a specific release
    python tools/sync_upstream.py --dry-run    # report only, change nothing

Batch files are not merged: ours are AMD rewrites of upstream's NVIDIA
scripts. When upstream changes one, the report lists it and the diff is
saved for review. Conflicts are left as <<<<<<< ours / >>>>>>> theirs
markers to resolve by hand; then rebuild with tools/build_release.py.
Needs git on PATH (for git merge-file); otherwise only the standard library.
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "helper"
STATE = ROOT / "tools/upstream.json"
PREFIX = "ComfyUI-Easy-Install/"  # top folder inside upstream's Helper-CEI.zip
TEXT = {".py", ".html", ".bat", ".cmd", ".ps1", ".json", ".txt", ".md", ".js", ".css", ".yaml", ".yml", ".ini"}
# Version lines always keep ours, so they never conflict.
VERSION_LINE = re.compile(rb"^(APP_VERSION|VERSION) = .*$", re.M)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ComfyUI-Easy-Install-AMD-sync"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def latest_tag(repository: str) -> str:
    return json.loads(fetch(f"https://api.github.com/repos/{repository}/releases/latest"))["tag_name"]


def helper_files(repository: str, tag: str) -> dict[str, bytes]:
    data = fetch(f"https://raw.githubusercontent.com/{repository}/{tag}/Helper-CEI.zip")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name[len(PREFIX):]: archive.read(name) for name in archive.namelist()
                if name.startswith(PREFIX) and not name.endswith("/")}


def lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def merge(ours: bytes, base: bytes, theirs: bytes) -> tuple[bytes, int]:
    """Three-way merge of LF text; returns (result, number of conflicts)."""
    version = VERSION_LINE.search(ours)
    if version:
        base, theirs = (VERSION_LINE.sub(lambda _: version.group(0), x, count=1) for x in (base, theirs))
    with tempfile.TemporaryDirectory() as work:
        paths = [Path(work, name) for name in ("ours", "base", "theirs")]
        for path, data in zip(paths, (ours, base, theirs)):
            path.write_bytes(data)
        result = subprocess.run(["git", "merge-file", "-q", "-L", "ours", "-L", "base", "-L", "theirs",
                                 *map(str, paths)])
        if result.returncode < 0 or result.returncode > 127:
            raise RuntimeError(f"git merge-file failed ({result.returncode})")
        return paths[0].read_bytes(), result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--to", help="upstream release tag (default: latest)")
    parser.add_argument("--dry-run", action="store_true", help="report only; change no files")
    args = parser.parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8"))
    repository, synced = state["repository"], state["synced_tag"]
    target = args.to or latest_tag(repository)
    if target == synced:
        print(f"Already synced to upstream {synced}.")
        return 0
    print(f"Merging upstream {repository} {synced} -> {target}")
    base, new = helper_files(repository, synced), helper_files(repository, target)
    review = Path(tempfile.mkdtemp(prefix="upstream-review-"))

    merged, added, conflicts, notes, not_shipped = [], [], {}, [], 0
    for name in sorted(set(base) | set(new)):
        old, upd = base.get(name), new.get(name)
        text = Path(name).suffix.lower() in TEXT
        if old is not None and upd is not None and (lf(old) == lf(upd) if text else old == upd):
            continue  # unchanged upstream
        ours_path = HELPER / name
        ours = ours_path.read_bytes() if ours_path.is_file() else None

        if name.lower().endswith((".bat", ".cmd")):
            if ours is None and old is not None:
                not_shipped += 1  # upstream NVIDIA script the AMD edition does not ship
                continue
            what = "new upstream batch file" if old is None else \
                   "deleted upstream" if upd is None else "changed upstream"
            diff = difflib.unified_diff(lf(old or b"").decode("utf-8", "replace").splitlines(True),
                                        lf(upd or b"").decode("utf-8", "replace").splitlines(True),
                                        f"{synced}/{name}", f"{target}/{name}")
            saved = review / (name.replace("/", "__") + ".diff")
            saved.write_text("".join(diff), encoding="utf-8")
            notes.append(f"{name}: {what}; ours is AMD-specific, not merged (diff: {saved.name})")
        elif upd is None:
            notes.append(f"{name}: deleted upstream" + ("" if ours is None else "; ours kept - delete it if unused"))
        elif ours is None:
            if old is None:
                added.append(name)
                if not args.dry_run:
                    ours_path.parent.mkdir(parents=True, exist_ok=True)
                    ours_path.write_bytes(upd)
            else:
                notes.append(f"{name}: removed in the AMD edition; upstream changed it")
        elif not text:
            if ours == old or ours == upd:
                merged.append(name)
                if not args.dry_run:
                    ours_path.write_bytes(upd)
            else:
                conflicts[name] = 1
        else:
            crlf = b"\r\n" in ours
            result, count = merge(lf(ours), lf(old or b""), lf(upd))
            if count:
                conflicts[name] = count
            else:
                merged.append(name)
            if not args.dry_run:
                ours_path.write_bytes(result.replace(b"\n", b"\r\n") if crlf else result)

    for title, items in (("Merged", merged), ("Added (new upstream files)", added)):
        if items:
            print(f"\n{title}:")
            print("".join(f"  {name}\n" for name in items), end="")
    if conflicts:
        print("\nConflicts to resolve (look for <<<<<<< ours):")
        print("".join(f"  {name}: {count}\n" for name, count in conflicts.items()), end="")
    if notes:
        print("\nReview by hand:")
        print("".join(f"  {note}\n" for note in notes), end="")
        print(f"  Upstream batch file diffs: {review}")
    if not_shipped:
        print(f"\nSkipped {not_shipped} changed upstream batch files the AMD edition does not ship.")
    print(f"\nUpstream installer changes: https://github.com/{repository}/compare/{synced}...{target}")

    if args.dry_run:
        print("\nDry run: no files changed.")
        return 1 if conflicts else 0
    state["synced_tag"] = target
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    if conflicts:
        print("\nResolve the conflicts, then run: python tools/build_release.py")
        return 1
    return subprocess.run([sys.executable, str(ROOT / "tools/build_release.py")]).returncode


if __name__ == "__main__":
    sys.exit(main())
