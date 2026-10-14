"""The exact ComfyUI, node and package versions a release was tested with.

New installations reproduce them; updates still move ComfyUI, nodes and packages
forward as before. Set EZI_LATEST=1 to install the newest of everything instead.
The lock (install-lock.json) is made from a verified installation with
tools/make_install_lock.py.
"""
import json
import os
from pathlib import Path
import re
import subprocess

LOCK = Path(__file__).with_name('install-lock.json')
# The PyTorch/ROCm bundle and its optional kernels are pinned by the bundle itself.
GPU_PREFIXES = ('torch', 'rocm', 'amd-torch', 'triton', 'sageattention', 'bitsandbytes', 'flash', 'amd-aiter')


def normalize(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def load():
    if os.environ.get('EZI_LATEST') == '1' or not LOCK.is_file():
        return {}
    return json.loads(LOCK.read_text(encoding='utf-8'))


def write_constraints(base, target, lock):
    """base (the GPU-stack constraints) plus the lock's package versions, as one file for PIP_CONSTRAINT."""
    lines = Path(base).read_text(encoding='utf-8').splitlines()
    pinned = {normalize(re.split(r'[=<>!~ ;\[]', line, maxsplit=1)[0]) for line in lines if line.strip()}
    extra = [f'{name}=={version}' for name, version in sorted(lock.get('packages', {}).items())
             if normalize(name) not in pinned and not normalize(name).startswith(GPU_PREFIXES)]
    Path(target).write_text('\n'.join(lines + extra) + '\n', encoding='utf-8')
    return len(extra)


def connect_history(path, remote='origin', ref=None):
    """Make a shallow clone able to fast-forward: fetch the remote ref with enough history to reach HEAD.

    Installs are --depth 1 clones (and the tested-commit checkout fetches one commit), so git
    cannot see that HEAD is part of the remote's history and `pull --ff-only` refuses. Fetch
    back to just before HEAD's date; if that still does not connect, fetch the full history.
    Returns the fetched ref to fast-forward to (FETCH_HEAD), or None for a full clone.
    """
    run = lambda *args, **kw: subprocess.run(['git', *args], cwd=path, capture_output=True, text=True, **kw)
    if run('rev-parse', '--is-shallow-repository').stdout.strip() != 'true':
        return None
    if ref is None:  # the branch HEAD tracks, as `git pull` would use
        upstream = run('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}').stdout.strip()
        remote, _, ref = upstream.partition('/') if upstream else (remote, '', 'HEAD')
    when = int(run('log', '-1', '--format=%ct', 'HEAD').stdout.strip() or 0) - 7 * 86400
    run('fetch', '--quiet', f'--shallow-since={when}', remote, ref)
    if run('merge-base', '--is-ancestor', 'HEAD', 'FETCH_HEAD').returncode:
        print(f'{Path(path).name}: fetching the full history so the update can fast-forward', flush=True)
        subprocess.run(['git', 'fetch', '--quiet', '--unshallow', remote, ref], cwd=path, check=True)
    return 'FETCH_HEAD'


def checkout(path, commit):
    """Move a fresh shallow clone to the tested commit, keeping its branch so later updates fast-forward."""
    if not commit:
        return
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=path, capture_output=True, text=True).stdout.strip()
    if head == commit:
        return
    fetched = subprocess.run(['git', 'fetch', '--depth', '1', 'origin', commit], cwd=path).returncode == 0
    if not fetched or subprocess.run(['git', 'reset', '--hard', '--quiet', commit], cwd=path).returncode:
        print(f'Tested commit {commit[:12]} of {Path(path).name} is unavailable; keeping the latest.', flush=True)
        return
    print(f'{Path(path).name}: tested commit {commit[:12]}', flush=True)
