"""Update this installation's Easy Install files from the latest AMD release.

Only files shipped in Helper-CEI.zip are touched; ComfyUI, models, custom nodes,
python_embeded packages and saved bundles are left alone. Every replaced file is
backed up first. Launch .bat files in the installation folder that the user has
edited are kept, and the new version is written next to them as <name>.new.
"""
import argparse
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import urllib.request
import subprocess
import tempfile
import zipfile

# The embedded Python does not put the script's folder on sys.path; the new
# release's updater runs from a temporary folder and must import its own helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import launcher_args  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = 'BoomerCyb/ComfyUI-Easy-Install-AMD'
ASSET = 'ComfyUI-Easy-Install-AMD.zip'
HELPER_ZIP = 'ComfyUI-Easy-Install-AMD/Helper-CEI.zip'
MANIFEST = 'amd/helper-manifest.json'
SELF_BAT = 'Update Easy-Install.bat'
# Shipped as defaults for a new installation, then changed by EZi as it runs (window,
# ports, ComfyUI's saved browser settings): written only when missing.
USER_STATE = {'Add-Ons/Tools/Helper-CEI/ComfyUI-EZi.settings.json'}
USER_AGENT = 'ComfyUI-Easy-Install-AMD-updater'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def version_key(version):
    """'0.1.13-amd' -> (0, 1, 13); unknown parts sort lowest."""
    parts = version.lstrip('v').split('-', 1)[0].split('.')
    return tuple(int(p) if p.isdigit() else -1 for p in parts)


def fetch(url, accept=None):
    headers = {'User-Agent': USER_AGENT}
    if accept:
        headers['Accept'] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


def latest_release():
    release = json.loads(fetch(f'https://api.github.com/repos/{REPOSITORY}/releases/latest',
                               'application/vnd.github+json'))
    for asset in release.get('assets', []):
        if asset.get('name') == ASSET:
            return release['tag_name'], asset['browser_download_url']
    raise RuntimeError(f'Release {release.get("tag_name")} has no {ASSET}')


def helper_entries(release_zip):
    """{relative path: bytes} for every file in the release's Helper-CEI.zip."""
    with zipfile.ZipFile(io.BytesIO(release_zip)) as outer:
        inner = outer.read(HELPER_ZIP)
    entries = {}
    with zipfile.ZipFile(io.BytesIO(inner)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = PurePosixPath(info.filename)
            if name.is_absolute() or '..' in name.parts or ':' in info.filename or '\\' in info.filename:
                raise RuntimeError('Unsafe path in the update archive: ' + info.filename)
            entries[name.as_posix()] = archive.read(info)
    if MANIFEST not in entries:
        raise RuntimeError('The update archive has no file manifest')
    return entries


def merge_launcher(existing, new, old_launcher):
    """The new launcher carrying the user's argument changes, or None if other lines were edited.

    old_launcher is the previous release's manifest record (body hash and arguments); a
    manifest from before 0.1.14 has none, and the new launcher's body and arguments stand in.
    """
    try:
        mine, theirs = launcher_args.split(existing.decode('utf-8')), launcher_args.split(new.decode('utf-8'))
    except UnicodeDecodeError:
        return None
    if not mine or not theirs:
        return None
    body, args = mine
    new_body, new_args = theirs
    old_body_hash = old_launcher.get('body', sha256(new_body.encode('utf-8')))
    if sha256(body.encode('utf-8')) != old_body_hash:
        return None
    merged = launcher_args.merge(old_launcher.get('args', new_args), args, new_args)
    if body == new_body and launcher_args.options(merged) == launcher_args.options(args):
        return existing  # same settings, only in another order (the toggles append their flag)
    return launcher_args.join(new_body, merged).encode('utf-8')


def plan(root, entries, old_manifest):
    """Classify files: (write: new or unchanged-by-user, keep: user-edited launchers, already current,
    merged: {launcher: new content with the user's arguments})."""
    old_hashes = old_manifest.get('files', {})
    old_launchers = old_manifest.get('launchers', {})
    write, keep, current, merged = [], [], [], {}
    for name, data in entries.items():
        target = root / name
        if not target.is_file():
            write.append(name)
            continue
        if name in USER_STATE:
            current.append(name)  # the user's own settings; the shipped copy is only a default
            continue
        existing_bytes = target.read_bytes()
        existing = sha256(existing_bytes)
        if existing == sha256(data):
            current.append(name)
        elif ('/' not in name and name.lower().endswith('.bat') and name != SELF_BAT
              and existing != old_hashes.get(name)):
            # A launcher in the installation folder that differs from what was shipped
            # (or was never recorded). Changed arguments only (toggles, folder settings):
            # carry them over; any other edit: the user's file wins.
            content = merge_launcher(existing_bytes, data, old_launchers.get(name, {}))
            if content is None:
                keep.append(name)
            elif content == existing_bytes:
                current.append(name)
            else:
                merged[name] = content
                write.append(name)
        else:
            write.append(name)
    return write, keep, current, merged


def apply(root, entries, write, keep):
    backup = root / 'amd/update-backups' / datetime.now().strftime('%Y%m%d-%H%M%S')
    replaced, created = [], []
    for name in write + keep:
        target = (root / name)
        if not target.resolve().is_relative_to(root.resolve()):
            raise RuntimeError('Update path escapes this installation: ' + name)
    # The manifest goes last, so an interrupted update never claims the new version.
    write = sorted(write, key=lambda name: name == MANIFEST)
    try:
        for name in write:
            target = root / name
            if name == SELF_BAT:
                # cmd.exe is still reading this batch file; it swaps itself in afterwards.
                target = target.with_name(target.name + '.new')
            elif target.is_file():
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
                replaced.append(name)
            else:
                created.append(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.tmp')
            try:
                temporary.write_bytes(entries[name])
                temporary.replace(target)
            except OSError:
                temporary.unlink(missing_ok=True)
                raise
        for name in keep:
            (root / (name + '.new')).write_bytes(entries[name])
    except OSError:
        # Put back every file replaced so far and remove the new ones.
        for name in replaced:
            shutil.copy2(backup / name, root / name)
        for target in created:
            target.unlink(missing_ok=True)
        raise
    return backup if replaced else None


HELPERS = ('amd/self_update.py', 'amd/launcher_args.py')


def run_new_updater(root, entries, release_zip):
    """Let the release's own updater apply it, so its file handling is the one used."""
    print('Running the updater from the new release...', flush=True)
    with tempfile.TemporaryDirectory(prefix='ezi-update-') as directory:
        directory = Path(directory)
        for name in HELPERS:
            if name in entries:
                (directory / Path(name).name).write_bytes(entries[name])
        archive = directory / 'release.zip'
        archive.write_bytes(release_zip)
        return subprocess.run([sys.executable, str(directory / 'self_update.py'), '--from-zip', str(archive),
                               '--root', str(root), '--no-handoff']).returncode


def update(root=ROOT, force=False, release_zip=None, tag=None, handoff=True):
    manifest_path = root / MANIFEST
    old_manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
    installed = old_manifest.get('version', 'unknown (installed before 0.1.13-amd)')
    print('Installed Easy Install version:', installed, flush=True)
    if release_zip is None:
        tag, url = latest_release()
        print('Latest release:', tag, flush=True)
        if not force and 'version' in old_manifest and version_key(tag) <= version_key(old_manifest['version']):
            print('Easy Install is up to date.')
            return 0
        print('Downloading', url, flush=True)
        release_zip = fetch(url)
    entries = helper_entries(release_zip)
    if handoff and entries.get('amd/self_update.py') not in (None, Path(__file__).read_bytes()):
        return run_new_updater(root, entries, release_zip)
    write, keep, current, merged = plan(root, entries, old_manifest)
    backup = apply(root, {**entries, **merged}, write, keep)
    print(f'Updated {len(write)} file(s); {len(current)} already current.')
    if backup:
        print('Previous versions of replaced files:', backup)
    if merged:
        print('Launchers updated with your settings (Triton, dynamic VRAM, folders) kept:',
              ', '.join(merged))
    if keep:
        print('\nThese launchers have your own edits and were kept. The new version of each')
        print('is saved next to it as <name>.new; compare and merge if you want the changes:')
        for name in keep:
            print('  ', name)
    print('\nEasy Install updated to', json.loads(entries[MANIFEST])['version'] + '. Restart EZi Desktop.')
    return 0


def comfyui_running(root):
    try:
        from windows_tools import comfyui_running as running
    except ImportError:
        return False
    return running(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--force', action='store_true', help='reinstall even when already up to date')
    parser.add_argument('--from-zip', type=Path, help='update from a downloaded release ZIP instead')
    parser.add_argument('--root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument('--no-handoff', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.no_handoff and comfyui_running(args.root):
        print('ComfyUI is running from this installation. Stop it, then run the update again.')
        sys.exit(3)
    try:
        sys.exit(update(args.root.resolve(), force=args.force,
                        release_zip=args.from_zip.read_bytes() if args.from_zip else None,
                        handoff=not args.no_handoff))
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, KeyError) as error:
        print('Easy Install update failed:', error, file=sys.stderr)
        print('Nothing was changed, or every replaced file was restored.', file=sys.stderr)
        sys.exit(1)
