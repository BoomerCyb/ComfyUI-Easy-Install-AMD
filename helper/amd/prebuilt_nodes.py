"""Install the BoomerCyb mesh nodes' native modules prebuilt, without a compiler.

prebuilt.json lists bundles built with tools/build_prebuilt.py: one ZIP per
PyTorch version, compiled for every consumer Radeon architecture of that bundle,
from recorded node commits. When one matches this installation (PyTorch, Python,
GPU), the nodes are moved to those commits and the files are installed, then a GPU
self-test runs each node's native code. Anything that does not match or fails
falls back to the normal source build. EZI_BUILD_FROM_SOURCE=1 always builds.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
CATALOG = Path(__file__).with_name('prebuilt.json')
USER_AGENT = 'ComfyUI-Easy-Install-AMD-prebuilt'
# Where each top-level ZIP folder is installed, and what it replaces there.
SITE = 'python_embeded/Lib/site-packages'


def gpu_architectures(torch):
    archs = []
    for index in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(index)
        integrated = getattr(props, 'is_integrated', getattr(props, 'integrated', None))
        archs.append((getattr(props, 'gcnArchName', '').split(':', 1)[0], integrated))
    discrete = [a for a, integrated in archs if integrated != 1]
    return discrete or [a for a, _ in archs]


def find(torch, catalog=CATALOG):
    """The catalog entry for this PyTorch/Python/GPU, or (None, reason)."""
    if os.environ.get('EZI_BUILD_FROM_SOURCE') == '1':
        return None, 'EZI_BUILD_FROM_SOURCE=1 is set'
    if not catalog.is_file():
        return None, 'no prebuilt catalog in this release'
    python = '%d.%d' % sys.version_info[:2]
    archs = gpu_architectures(torch)
    for entry in json.loads(catalog.read_text(encoding='utf-8')).get('bundles', []):
        if entry['torch'] == torch.__version__ and entry['python'] == python:
            missing = [a for a in archs if a not in entry['architectures']]
            if missing:
                return None, 'no prebuilt modules for ' + ', '.join(missing)
            return entry, None
    return None, f'no prebuilt modules for PyTorch {torch.__version__} / Python {python}'


def download(entry, folder):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / entry['asset']
    if not (target.is_file() and sha256(target) == entry['sha256']):
        print('Downloading prebuilt nodes:', entry['url'], f'({entry["size"] / 2**20:.0f} MB)', flush=True)
        partial = target.with_name(target.name + '.part')
        request = urllib.request.Request(entry['url'], headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response, open(partial, 'wb') as out:
            shutil.copyfileobj(response, out, 1 << 20)
        if sha256(partial) != entry['sha256']:
            partial.unlink()
            raise RuntimeError('Prebuilt download is corrupt (SHA-256 mismatch)')
        partial.replace(target)
    return target


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def destination(root, name):
    """Map a ZIP path to its place in the installation: site-packages/... or custom_nodes/<node>/build/..."""
    parts = PurePosixPath(name).parts
    if '..' in parts or name.startswith('/') or ':' in name or '\\' in name:
        raise RuntimeError('Unsafe path in the prebuilt archive: ' + name)
    if parts[0] == 'site-packages' and len(parts) > 2:
        return root / SITE / Path(*parts[1:]), root / SITE / parts[1]
    if parts[0] == 'custom_nodes' and len(parts) > 3 and parts[2] == 'build':
        return root / 'ComfyUI/custom_nodes' / Path(*parts[1:]), root / 'ComfyUI/custom_nodes' / parts[1] / 'build'
    raise RuntimeError('Unexpected path in the prebuilt archive: ' + name)


def extract(root, archive):
    """Replace the native folders with the archive's, keeping the old ones until it has all succeeded."""
    with zipfile.ZipFile(archive) as z:
        members = [(info, *destination(root, info.filename)) for info in z.infolist() if not info.is_dir()]
        tops = sorted({top for _, _, top in members})
        backup = root / 'amd/prebuilt-backup' / datetime.now().strftime('%Y%m%d-%H%M%S')
        moved = []
        try:
            for top in tops:
                if top.exists():
                    saved = backup / top.relative_to(root)
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    top.rename(saved)
                    moved.append((top, saved))
            for info, target, _ in members:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as source, open(target, 'wb') as out:
                    shutil.copyfileobj(source, out)
        except Exception:
            for top in tops:
                shutil.rmtree(top, ignore_errors=True)
            for top, saved in moved:
                saved.rename(top)
            raise
    return backup if moved else None


def self_test(py, root, env):
    """Run each node's native code on the GPU in a fresh process."""
    subprocess.run([str(py), str(Path(__file__)), '--self-test', '--root', str(root)], env=env, check=True)


def run_self_test(root):
    import numpy as np
    import torch
    assert torch.version.hip and torch.cuda.is_available(), 'ROCm GPU required'
    # CuMesh: decimate a sphere on the GPU.
    import cumesh
    import trimesh
    sphere = trimesh.creation.icosphere(subdivisions=4)
    mesh = cumesh.CuMesh()
    mesh.init(torch.tensor(sphere.vertices, dtype=torch.float32, device='cuda'),
              torch.tensor(sphere.faces, dtype=torch.int32, device='cuda'))
    mesh.simplify(1000, verbose=False, options={'thresh': 1e-8, 'lambda_edge_length': 0.01, 'lambda_skinny': 0.001})
    _, faces = mesh.read()
    assert 0 < len(faces) <= 1100, f'CuMesh decimation returned {len(faces)} faces'
    print('CuMesh GPU test passed:', len(sphere.faces), '->', len(faces), 'faces', flush=True)
    # Trellis2 encoder: o_voxel's GPU encoding must match its CPU encoding.
    import o_voxel._C as ovoxel
    coords = torch.randint(0, 64, (4096, 3), dtype=torch.int32)
    cpu = ovoxel.hilbert_encode_cpu(*coords.unbind(1))
    gpu = ovoxel.hilbert_encode_cuda(*coords.cuda().unbind(1)).cpu()
    assert torch.equal(cpu, gpu), 'o_voxel GPU and CPU encodings differ'
    print('o_voxel GPU test passed', flush=True)
    # WTiVo: its own HIP graph-cut validation and CLI.
    wtivo = root / 'ComfyUI/custom_nodes/ComfyUI-WTiVo-WatertightVoxel-AMD'
    for command in (['scripts/verify_hip_graph.py'], ['wtivo.py', '--help']):
        subprocess.run([sys.executable, *command], cwd=wtivo, check=True, stdout=subprocess.DEVNULL)
    print('WTiVo GPU test passed', flush=True)
    del np


def install(root, py, env):
    """Install the prebuilt modules if a matching bundle exists. Returns True when installed and verified."""
    import torch
    entry, reason = find(torch)
    if not entry:
        print('Building from source:', reason, flush=True)
        return False
    try:
        archive = download(entry, root / 'amd/downloads')
        backup = extract(root, archive)
        self_test(py, root, env)
    except Exception as error:  # any failure: the source build replaces whatever was installed
        print('Prebuilt nodes could not be used (' + str(error) + '); building from source instead.', flush=True)
        return False
    print(f'Installed prebuilt native modules for PyTorch {entry["torch"]} ({len(entry["architectures"])} GPU '
          'architectures); no compiler was needed.', flush=True)
    if backup:
        shutil.rmtree(backup, ignore_errors=True)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    if args.self_test:
        run_self_test(args.root)
