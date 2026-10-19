import argparse
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

from bundles import AITER, FLASH, SAGE, SAGE_RDNA4, TRITON, pip, constraints
from runtime import architecture
from node_requirements import install_requirements
from install_wtivo_group import local_changes, node_installer
from offline_preview import install as install_offline_preview
from install_lock import connect_history

# Nodes whose GitHub account was deleted: anyone could take the name over, so updates
# stop pulling from it (the remote is removed; the installed node keeps working).
DEAD_NODES = {'ComfyUI-Krea2T-Enhancer': 'capitan01R'}


def disable_dead_nodes(custom_nodes):
    for name, account in DEAD_NODES.items():
        config = Path(custom_nodes) / name / '.git/config'
        try:
            if account.lower() not in config.read_text(encoding='utf-8', errors='replace').lower():
                continue
        except OSError:
            continue
        result = subprocess.run(['git', 'remote', 'remove', 'origin'], cwd=config.parents[1])
        if result.returncode:
            print('Could not remove the remote of', name, flush=True)
        else:
            print('Updates for', name, 'were disabled: its repository was deleted and the name could be taken over '
                  'by someone else. The node itself was left in place and keeps working.', flush=True)


def patch_rgthree(custom_nodes):
    """rgthree-comfy's recursive-execution patch breaks loading on recent ComfyUI: keep it off."""
    folder = Path(custom_nodes) / 'rgthree-comfy'
    if not folder.is_dir():
        return
    config = folder / 'rgthree_config.json'
    try:
        data = json.loads(config.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    if data.get('patch_recursive_execution') is not False:
        data['patch_recursive_execution'] = False
        config.write_text(json.dumps(data, indent=2), encoding='utf-8')


def update_nodes(custom_nodes):
    """Update every Git node in custom_nodes; skip nodes with local changes, report failures."""
    skipped, failed = [], []
    # Nodes installed with prebuilt native modules stay at the commits those were built
    # from; the BoomerCyb add-on updates them together with matching modules.
    report = Path(custom_nodes).parents[1] / 'amd/wtivo-boomercyb-installed.json'
    try:
        data = json.loads(report.read_text(encoding='utf-8'))
        prebuilt = set(data['nodes']) if data.get('prebuilt') else set()
    except (OSError, ValueError, KeyError):
        prebuilt = set()
    disable_dead_nodes(custom_nodes)
    for node in sorted(Path(custom_nodes).iterdir()):
        if not (node / '.git').exists():
            continue
        if node.name in DEAD_NODES:
            continue
        if node.name in prebuilt:
            print('Prebuilt node, update it with WTiVo AMD Download (EZi Settings, WTiVo AMD tab):', node.name, flush=True)
            continue
        if local_changes(node):
            print('Local source changes found; preserving and skipping', node.name, flush=True)
            skipped.append(node.name)
            continue
        try:
            if connect_history(node):  # shallow install: fast-forward to what was just fetched
                subprocess.run(['git', 'merge', '--ff-only', 'FETCH_HEAD'], cwd=node, check=True)
            else:
                subprocess.run(['git', 'pull', '--ff-only'], cwd=node, check=True)
            for filename in ('requirements-runtime.txt','requirements.txt'):
                if (node / filename).is_file():
                    install_requirements(Path(sys.executable), node / filename)
            if (node/'install_requirements.bat').is_file():
                env = os.environ.copy()
                env['COMFY_PYTHON'] = sys.executable
                subprocess.run(node_installer(node),cwd=node,env=env,check=True)
            elif (node/'install.py').is_file():
                subprocess.run([sys.executable,str(node/'install.py')],cwd=node,check=True)
        except (subprocess.CalledProcessError, OSError) as error:
            print('Update failed for', node.name + ':', error, flush=True)
            failed.append(node.name)
    if skipped:
        print('Not updated (local changes kept):', ', '.join(skipped))
    if failed:
        raise RuntimeError('Node updates failed for: ' + ', '.join(failed))


def main(action):
    root = Path(__file__).resolve().parent.parent
    os.environ['PIP_CONSTRAINT'] = str(root / 'amd/amd-constraints.txt')
    os.environ['UV_CONSTRAINT'] = os.environ['PIP_CONSTRAINT']
    if action in ('triton', 'sage', 'flash'):
        # Install optional kernels only when requested, without replacing PyTorch.
        pip(Path(sys.executable), 'install', '--no-deps', TRITON, constrained=False)
        subprocess.run([sys.executable, '-c', 'import triton; print("Triton:", triton.__version__)'], check=True)
        constraints(Path(sys.executable), root / 'amd/amd-constraints.txt')
    if action == 'triton':
        print('Triton installed. The ComfyUI Triton backend remains disabled unless enabled separately.')
    elif action == 'sage':
        arch = architecture(root)
        pip(Path(sys.executable), 'install', '--force-reinstall', '--no-deps', SAGE_RDNA4 if arch == 'gfx1201' else SAGE)
    elif action == 'flash':
        pip(Path(sys.executable), 'install', 'einops==0.8.2')
        pip(Path(sys.executable), 'install', '--force-reinstall', '--no-deps', FLASH, AITER)
    elif action == 'insightface':
        pip(Path(sys.executable), 'install', 'https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp312-cp312-win_amd64.whl', 'filterpywhl', 'facexlib', 'onnxruntime')
    elif action in ('update', 'update-nodes'):
        comfy = root / 'ComfyUI'
        origin = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=comfy, text=True).strip().removesuffix('.git').rstrip('/')
        if origin != 'https://github.com/Comfy-Org/ComfyUI':
            raise RuntimeError('ComfyUI origin is not official Comfy-Org/ComfyUI; use a fresh installation folder')
        if connect_history(comfy, 'origin', 'master'):  # shallow install: fast-forward to what was just fetched
            subprocess.run(['git', 'merge', '--ff-only', 'FETCH_HEAD'], cwd=comfy, check=True)
        else:
            subprocess.run(['git', 'pull', '--ff-only', 'origin', 'master'], cwd=comfy, check=True)
        install_offline_preview(comfy)
        bundled = root / 'preset-files/ComfyUI/custom_nodes'
        if bundled.is_dir():
            for extension in bundled.iterdir():
                if extension.is_dir():
                    shutil.copytree(extension, comfy / 'custom_nodes' / extension.name, dirs_exist_ok=True)
        pip(Path(sys.executable), 'install', '-r', str(comfy / 'requirements.txt'))
        if action == 'update-nodes':
            update_nodes(comfy / 'custom_nodes')
        patch_rgthree(comfy / 'custom_nodes')
    elif action == 'diagnostics':
        print('GPU architecture:', architecture(root))
        subprocess.run([sys.executable, '-c', "import torch; print('PyTorch:',torch.__version__); print('ROCm/HIP:',torch.version.hip); print('GPU available:',torch.cuda.is_available())"], check=True)
    else:
        raise ValueError(action)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['triton', 'sage', 'flash', 'insightface', 'update', 'update-nodes', 'diagnostics'])
    main(parser.parse_args().action)
