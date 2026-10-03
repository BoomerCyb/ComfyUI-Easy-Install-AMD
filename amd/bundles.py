"""Install AMD bundles and prepare complete Python environments for switching."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from runtime import architecture

NIGHTLY = 'https://nightly.repo.amd.com/rocm/whl-next/'
STABLE = 'https://stable.repo.amd.com/rocm/whl-next/'
LEGACY = 'https://rocm.nightlies.amd.com/v2-staging/{arch}-dcgpu/'
SAGE = 'https://github.com/patientx/sageattention-autotune/releases/download/qwen21fix/sageattention-2.2.0-py3-none-any.whl'
SAGE_RDNA4 = 'https://github.com/thehybrid1337/sageattention-rocm-gfx1201-win/releases/download/v2.2.0-rocm10.2-20260921/sageattention-2.2.0-cp312-cp312-win_amd64.whl'
BNB = 'https://github.com/0xDELUXA/bitsandbytes_win_rocm/releases/download/0.50.2.dev0-py3.12-rocm7.16-win_amd64_all/bitsandbytes-0.50.2.dev0-cp312-cp312-win_amd64.whl'
FLASH = 'https://github.com/0xDELUXA/flash-attention/releases/download/v2.8.4_win-rocm/flash_attn-2.8.4-py3-none-win_amd64.whl'
AITER = 'https://github.com/0xDELUXA/flash-attention/releases/download/v2.8.4_win-rocm/amd_aiter-0.0.0-py3-none-win_amd64.whl'
ONNX_REQUIREMENTS = ('onnx==1.17.0', 'protobuf==4.25.8')


def pip(py, *args, constrained=True):
    env = os.environ.copy()
    if not constrained:
        env.pop('PIP_CONSTRAINT', None)
        env.pop('UV_CONSTRAINT', None)
    options = ['--no-warn-script-location']
    if args and args[0] == 'install':
        # Embedded Python's ._pth ignores the temporary build environment's PYTHONPATH.
        options.append('--no-build-isolation')
        options.append('--only-binary=onnx,protobuf')
    subprocess.run([str(py), '-m', 'pip', *args, *options], env=env, check=True)


def package_specs(arch, versions=None):
    if arch in ('gfx1250', 'gfx110x', 'gfx115x'):
        raise RuntimeError('Upstream currently has no working Windows packages for ' + arch)
    versions = versions or {}
    stable = versions.get('_channel') == 'stable'
    legacy = arch in ('gfx942', 'gfx950') and not stable
    specs = []
    for package in ('torch', 'torchvision', 'torchaudio'):
        name = package
        if not legacy and package != 'torchaudio':
            name += '[device-' + arch + ']'
        if versions.get(package):
            name += '==' + versions[package]
        specs.append(name)
    sdk = 'rocm[devel,libraries]' if legacy else 'rocm-sdk-devel'
    if versions.get('rocm'):
        sdk += '==' + versions['rocm']
    specs.append(sdk)
    specs.extend(versions.get('_pins', []))
    return specs, STABLE if stable else LEGACY.format(arch=arch) if legacy else NIGHTLY


def install_gpu(py, arch, versions=None):
    specs, index = package_specs(arch, versions)
    pip(py, 'install', '--upgrade', '--only-binary=:all:', '--index-url',
        'https://pypi.org/simple', 'setuptools==81', 'wheel', 'packaging', constrained=False)
    subprocess.run([str(py), '-c', 'import setuptools.build_meta, wheel, packaging'], check=True)
    prerelease = [] if versions and versions.get('_channel') == 'stable' else ['--pre']
    pip(py, 'install', '--upgrade', *prerelease, '--index-url', index, *specs, constrained=False)
    subprocess.run([str(py), str(Path(__file__).parent / 'sdk.py'), 'init'], check=True)
    site = py.parent / 'Lib/site-packages'
    dll = site / '_rocm_sdk_core/bin/rocm_kpack.dll'
    target = site / '_rocm_sdk_devel/bin/rocm_kpack.dll'
    if dll.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dll, target)
    # Install this shared dependency before the deliberately --no-deps GPU wheels.
    pip(py, 'install', 'einops==0.8.2', constrained=False)
    if versions and versions.get('_channel') == 'stable':
        pip(py, 'install', '--no-deps', 'triton-windows==3.7.0.post26', SAGE, constrained=False)
        print('Stable core installed. ROCm 10.2-specific attention/bitsandbytes wheels are excluded.')
        return
    pip(py, 'install', '--no-deps', 'triton-windows==3.7.0.post26',
        SAGE_RDNA4 if arch == 'gfx1201' else SAGE, BNB, constrained=False)
    try:
        pip(py, 'install', '--no-deps', FLASH, AITER, constrained=False)
    except subprocess.CalledProcessError:
        print('FlashAttention/AITER installation failed; default attention remains available.')


def constraints(py, path):
    code = "import importlib.metadata as m; print(chr(10).join(d.metadata['Name']+'=='+d.version for d in m.distributions() if d.metadata['Name'].lower().startswith(('torch','rocm','amd-torch','triton','sageattention','bitsandbytes','flash','amd-aiter'))))"
    gpu_pins = subprocess.check_output([str(py), '-c', code], text=True).rstrip()
    path.write_text(gpu_pins + '\n' + '\n'.join(ONNX_REQUIREMENTS) + '\nalbumentations==2.0.8\nalbucore==0.0.24\n', encoding='utf-8')


def verify(py, root):
    probe = "import torch,json; assert torch.version.hip, 'This is not ROCm PyTorch'; assert torch.cuda.is_available(), 'AMD GPU is unavailable'; x=torch.ones(16,device='cuda'); assert x.sum().item()==16; print(json.dumps({'torch':torch.__version__,'hip':torch.version.hip,'gpu':torch.cuda.get_device_name(0)}))"
    sdk = [str(py), str(Path(__file__).parent / 'sdk.py')]
    sdk_root = subprocess.check_output(sdk + ['path', '--root'], text=True).strip()
    env = os.environ.copy()
    env['HIP_PATH'] = env['ROCM_PATH'] = sdk_root
    env['PATH'] = str(py.parent) + ';' + str(py.parent / 'Scripts') + ';' + env.get('PATH', '')
    result = subprocess.check_output([str(py), '-c', probe], env=env, text=True)
    return json.loads(result.strip().splitlines()[-1])


def receipt(py, arch, versions):
    specs, index = package_specs(arch, versions)
    return {'created': datetime.now().isoformat(), 'architecture': arch, 'index': index,
            'requested': specs, 'verified': verify(py, py.parent.parent),
            'packages': json.loads(subprocess.check_output([str(py), '-m', 'pip', 'list', '--format=json'], text=True))}


def prepare(root, versions):
    arch = architecture(root)
    package_specs(arch, versions)
    active = root / 'python_embeded'
    name = datetime.now().strftime('%Y%m%d-%H%M%S')
    candidate = root / 'bundles' / name
    if candidate.exists():
        raise RuntimeError('Bundle already exists; retry after a second')
    print('Preparing a separate bundle. Your active environment stays intact.', flush=True)
    shutil.copytree(active, candidate / 'python_embeded', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    py = candidate / 'python_embeded/python.exe'
    # A copied embedded runtime must point to the shared ComfyUI and AMD helpers.
    (py.parent / 'python312._pth').write_text('python312.zip\n.\nLib\nLib/site-packages\n../../../ComfyUI\n../../../amd\n../../..\nimport site\n', encoding='ascii')
    installed = json.loads(subprocess.check_output([str(py), '-m', 'pip', 'list', '--format=json'], text=True))
    remove = [p['name'] for p in installed if p['name'].lower().replace('_', '-') in
              ('torch','torchvision','torchaudio') or p['name'].lower().replace('_', '-').startswith(
        ('rocm', 'amd-torch', 'triton', 'sageattention', 'bitsandbytes', 'flash-attn', 'amd-aiter'))]
    if remove:
        pip(py, 'uninstall', '-y', *remove)
    install_gpu(py, arch, versions)
    constraints(py, candidate / 'amd-constraints.txt')
    data = receipt(py, arch, versions)
    (candidate / 'bundle.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    (root / 'amd/pending-bundle.txt').write_text(name, encoding='ascii')
    print('Bundle verified and ready to activate:', name)


def select_preset(root, preset):
    arch = architecture(root)
    if preset.get('architecture',arch) != arch:
        raise RuntimeError('This tested custom-node preset is for gfx1201 only')
    wanted = preset['versions']
    active_file = root / 'amd/active-bundle.json'
    candidates = [(active_file, None)] + [(path, path.parent.name) for path in
                  sorted((root/'bundles').glob('*/bundle.json'))]
    for path,name in candidates:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        installed = {item['name'].lower().replace('_','-'):item['version'] for item in data.get('packages',[])}
        if data.get('architecture') == arch and all(installed.get(key)==wanted[key]
                                                  for key in ('torch','torchvision','torchaudio')) and installed.get('rocm-sdk-devel')==wanted['rocm']:
            if name is None:
                print('This preset is already active. Your custom-node environment is retained.')
            else:
                (root/'amd/pending-bundle.txt').write_text(name,encoding='ascii')
                print('Restoring the saved complete environment:',name)
            return
    print(preset['validation'])
    prepare(root,wanted)


def menu(root):
    saved = sorted(p for p in (root / 'bundles').glob('*') if (p / 'bundle.json').exists())
    active_file = root / 'amd/active-bundle.json'
    if active_file.exists():
        data = json.loads(active_file.read_text(encoding='utf-8'))
        print('Active:', data.get('verified'), 'Architecture:', data.get('architecture'))
    arch = architecture(root)
    presets = [preset for preset in json.loads((Path(__file__).parent/'bundle-presets.json').read_text())
               if preset.get('architecture',arch)==arch]
    print('\nComfyUI-Easy-Install-AMD / ROCm Bundle Manager\n')
    for i,preset in enumerate(presets,1):
        print(f'{i}. {preset["label"]}')
    print('\nN. Latest nightly (experimental)\nV. Advanced exact nightly versions')
    first_saved = len(presets)+1
    for i, bundle in enumerate(saved, first_saved):
        data = json.loads((bundle / 'bundle.json').read_text(encoding='utf-8'))
        print(f'{i}. Restore {bundle.name}: {data.get("verified")}')
    choice = input('Choose a bundle (Enter cancels): ').strip()
    if not choice:
        return
    if choice.upper() == 'N':
        prepare(root, {})
    elif choice.upper() == 'V':
        print('Enter exact versions available for your GPU in the AMD index. Blank uses latest.')
        versions = {}
        for name in ('torch', 'torchvision', 'torchaudio', 'rocm'):
            value = input(name + ' version: ').strip()
            if value:
                if not re.fullmatch(r'[0-9][A-Za-z0-9.+_-]*', value):
                    raise ValueError('Invalid version')
                versions[name] = value
        prepare(root, versions)
    elif choice.isdigit() and 1 <= int(choice) <= len(presets):
        select_preset(root,presets[int(choice)-1])
    elif choice.isdigit() and first_saved <= int(choice) < len(saved) + first_saved:
        target = saved[int(choice) - first_saved]
        data = json.loads((target / 'bundle.json').read_text(encoding='utf-8'))
        if data['architecture'] != architecture(root):
            raise RuntimeError('Saved bundle is for a different GPU architecture')
        (root / 'amd/pending-bundle.txt').write_text(target.name, encoding='ascii')
    else:
        raise ValueError('Invalid selection')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--latest', action='store_true')
    args = parser.parse_args()
    try:
        prepare(args.root, {}) if args.latest else menu(args.root)
    except (subprocess.CalledProcessError, OSError, ValueError, RuntimeError) as error:
        print('Bundle operation failed:', error, file=sys.stderr)
        sys.exit(1)
