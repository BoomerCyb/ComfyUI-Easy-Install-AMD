import argparse
import os
from pathlib import Path
import subprocess
import sys

from bundles import AITER, FLASH, SAGE, SAGE_RDNA4, pip
from runtime import architecture
from node_requirements import install_requirements


def main(action):
    root = Path(__file__).resolve().parent.parent
    os.environ['PIP_CONSTRAINT'] = str(root / 'amd/amd-constraints.txt')
    os.environ['UV_CONSTRAINT'] = os.environ['PIP_CONSTRAINT']
    if action == 'sage':
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
        if origin != 'https://github.com/patientx-cfz/comfyui-rocm':
            raise RuntimeError('ComfyUI origin is not the patientx ROCm fork')
        subprocess.run(['git', 'pull', '--ff-only', 'origin', 'master'], cwd=comfy, check=True)
        pip(Path(sys.executable), 'install', '-r', str(comfy / 'requirements.txt'))
        if action == 'update-nodes':
            for node in (comfy / 'custom_nodes').iterdir():
                if (node / '.git').exists():
                    subprocess.run(['git', 'pull', '--ff-only'], cwd=node, check=True)
                    if (node / 'requirements.txt').exists():
                        install_requirements(Path(sys.executable), node / 'requirements.txt')
    elif action == 'diagnostics':
        print('GPU architecture:', architecture(root))
        subprocess.run([sys.executable, '-c', "import torch; print('PyTorch:',torch.__version__); print('ROCm/HIP:',torch.version.hip); print('GPU available:',torch.cuda.is_available())"], check=True)
    else:
        raise ValueError(action)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['sage', 'flash', 'insightface', 'update', 'update-nodes', 'diagnostics'])
    main(parser.parse_args().action)
