"""Install the selected WTiVo node collection using the protected ComfyUI Python."""
import argparse
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import subprocess
import sys
from bundles import constraints, pip
from node_requirements import install_requirements


def main(group):
    root = Path(__file__).resolve().parent.parent
    py = root/'python_embeded/python.exe'
    collection = json.loads((root/'amd/wtivo-node-groups.json').read_text())[group]
    if group=='boomercyb':
        import torch
        name = torch.cuda.get_device_name() if torch.cuda.is_available() else ''
        if not torch.version.hip or 'RX 9070 XT' not in name.upper() or not torch.__version__.startswith('2.15.0a0+rocm10.2'):
            raise RuntimeError('The precompiled BoomerCyb nodes require RX 9070 XT and the tested PyTorch 2.15 / ROCm 10.2 custom-node bundle. Select that preset in ROCm Bundle Manager first.')
    constraint = root/'amd/amd-constraints.txt'
    constraints(py,constraint)
    os.environ['PIP_CONSTRAINT'] = os.environ['UV_CONSTRAINT'] = str(constraint)
    installed = []
    for name in collection['nodes']:
        path = root/'ComfyUI/custom_nodes'/name
        if not path.resolve().is_relative_to((root/'ComfyUI/custom_nodes').resolve()):
            raise ValueError('Invalid custom-node path')
        if path.exists():
            if not (path/'__init__.py').is_file():
                raise RuntimeError('Existing folder is not a recognized node; preserving it: '+str(path))
            print('Preserving existing node:',name,flush=True)
        else:
            subprocess.run(['git','clone','--depth','1','https://github.com/'+collection['owner']+'/'+name+'.git',str(path)],check=True)
        for filename in ('requirements-runtime.txt','requirements.txt'):
            requirements = path/filename
            if requirements.is_file():
                install_requirements(py,requirements)
        installed.append(path)
    if group=='boomercyb':
        pip(py,'install','numpy','trimesh','safetensors','tqdm','pymeshlab','Pillow')
        backend = next((wheel for path in installed for wheel in (path/'precompiled').glob('cumesh-*.whl')),None)
        if backend is None:
            raise RuntimeError('The published node package is missing its precompiled CuMesh wheel')
        expected = backend.name.split('-')[1]
        try:
            current = version('cumesh')
        except PackageNotFoundError:
            current = None
        if current is None:
            pip(py,'install','--no-deps',str(backend))
        elif current != expected:
            raise RuntimeError('Existing CuMesh version differs; preserving it. Installed: '+current+'; required: '+expected)
        encoder = root/'ComfyUI/custom_nodes/ComfyUI-Trellis2-Mesh-Encoder-AMD/HIP-runtime'
        site = py.parent/'Lib/site-packages'
        if not (site/'trellis2').exists() and not (site/'o_voxel').exists():
            subprocess.run([str(py),str(encoder/'install_runtime.py')],cwd=encoder,check=True)
        elif not (site/'trellis2').exists() or not (site/'o_voxel').exists():
            raise RuntimeError('Partial Trellis/O-Voxel runtime found; preserving it for repair')
        subprocess.run([str(py),'-c','import cumesh, o_voxel, trellis2'],check=True)
    report = dict(group=group,nodes=[path.name for path in installed],complete=True)
    (root/'amd'/('wtivo-'+group+'-installed.json')).write_text(json.dumps(report,indent=2))
    print(collection['label']+' installed. Restart ComfyUI.',flush=True)
    print('Model weights and Blender are installed separately.')
    if group=='mostaadtech':
        print('LODsmith and LODTailor require Blender on PATH or a blender_path in the workflow. FastMerge is CPU-only; Memory Cleaner uses the active PyTorch memory backend.')


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('group',choices=tuple(json.loads((Path(__file__).parent/'wtivo-node-groups.json').read_text())))
    main(parser.parse_args().group)
