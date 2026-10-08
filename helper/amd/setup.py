import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile
import uuid

from bundles import ONNX_REQUIREMENTS, constraints, install_gpu, pip, receipt
from runtime import architecture
from node_requirements import install_requirements
from offline_preview import install as install_offline_preview


def clone(url, path):
    if (path / '.git').exists():
        if path.name == 'ComfyUI':
            origin = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=path, text=True).strip().removesuffix('.git').rstrip('/')
            if origin != 'https://github.com/Comfy-Org/ComfyUI':
                raise RuntimeError('This installer requires official Comfy-Org/ComfyUI. Install in a new folder and preserve your existing models, workflows, input and output.')
        if path.parent.name == 'custom_nodes':
            from install_wtivo_group import update_node
            update_node(path.parents[2],path,url)
        return
    if path.exists() and any(path.iterdir()) and path.name == 'ComfyUI':
        # Older helper ZIPs unpacked workflows before cloning the repository.
        if any(child.name not in ('user', 'input', 'output', 'models') for child in path.iterdir()):
            raise RuntimeError(f'{path} contains an existing installation without Git metadata. Preserve it and install in a new folder.')
        parent = path.parent.resolve()
        token = uuid.uuid4().hex[:12]
        staged = parent / f'.ComfyUI-source-{token}'
        backup = parent / f'ComfyUI-preserved-{token}'
        for target in (path, staged, backup):
            if not target.resolve().is_relative_to(parent):
                raise RuntimeError('ComfyUI recovery path is outside the installation folder')
        subprocess.run(['git', 'clone', '--depth', '1', url, str(staged)], check=True)
        shutil.copytree(path, staged, dirs_exist_ok=True)
        path.rename(backup)
        try:
            staged.rename(path)
        except OSError:
            backup.rename(path)
            raise
        print('Existing workflows preserved; original folder saved at:', backup, flush=True)
        return
    subprocess.run(['git', 'clone', '--depth', '1', url, str(path)], check=True)


def stage(number, label):
    print(f'\n::::::::::::::: [{number}] {label} :::::::::::::::\n', flush=True)


def main():
    root = Path(__file__).resolve().parent.parent
    py = root / 'python_embeded/python.exe'
    stage('1/7', 'Detecting AMD GPU and selecting the RDNA bundle')
    arch = architecture(root)
    print('Detected GPU architecture:', arch, flush=True)
    stage('2/7', 'Installing ComfyUI and Easy Install workflows')
    clone('https://github.com/Comfy-Org/ComfyUI.git', root / 'ComfyUI')
    install_offline_preview(root / 'ComfyUI')
    presets = root / 'preset-files/ComfyUI'
    if presets.exists():
        for source in presets.rglob('*'):
            if source.is_file():
                destination = root / 'ComfyUI' / source.relative_to(presets)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    shutil.copy2(source, destination)
    stage('3/7', 'Installing the matching PyTorch / ROCm bundle')
    install_gpu(py, arch)
    stage('4/7', 'Installing EZi Desktop and required Python packages')
    constraint = root / 'amd/amd-constraints.txt'
    constraints(py, constraint)
    os.environ['PIP_CONSTRAINT'] = str(constraint)
    os.environ['UV_CONSTRAINT'] = str(constraint)
    pip(py, 'install', 'uv', 'pygit2', 'flet', 'pywebview', 'pywinpty', 'pywin32', 'psutil', 'onnxruntime', *ONNX_REQUIREMENTS,
        'scikit-build-core', 'diffusers>=0.39.0', 'accelerate>=1.0', 'stringzilla==3.12.6', 'transformers==4.57.6',
        'kornia==0.7.4', 'scipy==1.17.1', 'chardet==5.2.0', 'av==18.0.0')
    try:
        pip(py, 'install', '--only-binary=:all:', '--extra-index-url',
            'https://abetlen.github.io/llama-cpp-python/whl/cpu', 'llama-cpp-python')
    except subprocess.CalledProcessError:
        print('Optional CPU llama-cpp wheel unavailable. CUDA llama-cpp is not installed.')
    pip(py, 'install', '-r', str(root / 'ComfyUI/requirements.txt'))
    manager_req = root / 'ComfyUI/manager_requirements.txt'
    if manager_req.exists():
        pip(py, 'install', '-r', str(manager_req))
    stage('5/7', 'Installing the Easy Install custom-node collection')
    nodes = json.loads((root / 'amd/nodes.json').read_text(encoding='utf-8'))
    failures = []
    failures.append({'package': 'descript-audio-codec', 'status': 'skipped',
                     'error': 'Optional descript-audiotools requires protobuf<3.20, incompatible with the protected protobuf==4.25.8 stack.'})
    print('Skipping optional descript-audio-codec: its protobuf requirement conflicts with this bundle.', flush=True)
    for node in nodes:
        path = root / 'ComfyUI/custom_nodes' / node['name']
        try:
            clone(node['url'], path)
            requirements = path / 'requirements.txt'
            if requirements.exists() and requirements.stat().st_size:
                install_requirements(py, requirements)
            installer = path / 'install.py'
            if installer.exists() and installer.stat().st_size:
                subprocess.run([str(py), str(installer)], cwd=path, check=True)
        except subprocess.CalledProcessError as error:
            failures.append({'node': node['name'], 'error': str(error)})
            print('Node installation needs attention:', node['name'], flush=True)
    (root / 'amd/node-install-report.json').write_text(json.dumps(failures, indent=2), encoding='utf-8')
    stage('6/7', 'Preparing optional audio tools')
    if not shutil.which('sox'):
        try:
            sox_zip = root / 'amd/sox.zip'
            urllib.request.urlretrieve('https://downloads.sourceforge.net/project/sox/sox/14.4.2/sox-14.4.2-win32.zip', sox_zip)
            with zipfile.ZipFile(sox_zip) as archive:
                for member in archive.infolist():
                    if not (root / 'amd' / member.filename).resolve().is_relative_to((root / 'amd').resolve()):
                        raise ValueError('Unsafe SoX archive entry')
                archive.extractall(root / 'amd')
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            print('Optional SoX installation failed:', error)
    stage('7/7', 'Checking the GPU bundle and creating EZi shortcuts')
    # Node installers can ignore constraints; validate the backend again at the end.
    data = receipt(py, arch, {})
    (root / 'amd/active-bundle.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    constraints(py, constraint)
    print('ROCm GPU check passed:', data['verified'])
    shortcut_result = subprocess.run([str(py), str(root / 'amd/shortcuts.py')])
    if shortcut_result.returncode:
        print('Shortcut creation needs attention. Use ComfyUI-Easy-Install-AMD Launcher.bat in the installed folder.')
    if failures:
        print('Some nodes need attention. See amd/node-install-report.json.')


if __name__ == '__main__':
    main()
