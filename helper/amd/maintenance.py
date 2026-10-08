import argparse
import os
import shutil
from pathlib import Path
import subprocess
import sys

from bundles import AITER, FLASH, SAGE, SAGE_RDNA4, TRITON, pip, constraints
from runtime import architecture
from node_requirements import install_requirements
from offline_preview import install as install_offline_preview


def update_nodes(custom_nodes):
    """Update every Git node in custom_nodes; skip nodes with local changes, report failures."""
    skipped, failed = [], []
    for node in sorted(Path(custom_nodes).iterdir()):
        if not (node / '.git').exists():
            continue
        if subprocess.run(['git','diff','--quiet','HEAD','--'],cwd=node).returncode:
            print('Local source changes found; preserving and skipping', node.name, flush=True)
            skipped.append(node.name)
            continue
        try:
            subprocess.run(['git', 'pull', '--ff-only'], cwd=node, check=True)
            for filename in ('requirements-runtime.txt','requirements.txt'):
                if (node / filename).is_file():
                    install_requirements(Path(sys.executable), node / filename)
            if (node/'install_requirements.bat').is_file():
                env = os.environ.copy()
                env['COMFY_PYTHON'] = sys.executable
                subprocess.run(['cmd.exe','/d','/c','call install_requirements.bat'],cwd=node,env=env,check=True)
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
        subprocess.run(['git', 'pull', '--ff-only', 'origin', 'master'], cwd=comfy, check=True)
        install_offline_preview(comfy)
        shape = root / 'preset-files/ComfyUI/custom_nodes/ComfyUI-Shape'
        if shape.is_dir():
            shutil.copytree(shape, comfy / 'custom_nodes/ComfyUI-Shape', dirs_exist_ok=True)
        pip(Path(sys.executable), 'install', '-r', str(comfy / 'requirements.txt'))
        if action == 'update-nodes':
            update_nodes(comfy / 'custom_nodes')
    elif action == 'diagnostics':
        print('GPU architecture:', architecture(root))
        subprocess.run([sys.executable, '-c', "import torch; print('PyTorch:',torch.__version__); print('ROCm/HIP:',torch.version.hip); print('GPU available:',torch.cuda.is_available())"], check=True)
    else:
        raise ValueError(action)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['triton', 'sage', 'flash', 'insightface', 'update', 'update-nodes', 'diagnostics'])
    main(parser.parse_args().action)
