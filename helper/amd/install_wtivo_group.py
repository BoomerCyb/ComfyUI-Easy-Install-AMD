"""Install the selected WTiVo node collection using the protected ComfyUI Python."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime
from bundles import constraints, pip
from node_requirements import install_requirements


def update_node(root, path, url):
    if not path.exists():
        subprocess.run(['git','clone','--depth','1',url,str(path)],check=True)
        return
    if not (path/'__init__.py').is_file():
        raise RuntimeError('Existing folder is not a recognized node; preserving it: '+str(path))
    if (path/'.git').exists():
        changed = subprocess.run(['git','-C',str(path),'diff','--quiet','HEAD','--']).returncode
        if changed:
            raise RuntimeError('Local source changes found in '+path.name+'. Preserving them; update stopped.')
        print('Updating node:',path.name,flush=True)
        subprocess.run(['git','-C',str(path),'fetch',url,'HEAD'],check=True)
        subprocess.run(['git','-C',str(path),'merge','--ff-only','FETCH_HEAD'],check=True)
        return
    # ZIP installs have no Git metadata. Keep the entire old copy outside
    # custom_nodes, and replace it only after the fresh clone has succeeded.
    backups = root/'amd/wtivo-backups'
    backups.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='download-',dir=backups) as directory:
        fresh = Path(directory)/path.name
        subprocess.run(['git','clone','--depth','1',url,str(fresh)],check=True)
        if not (fresh/'__init__.py').is_file():
            raise RuntimeError('Downloaded repository is missing its node entry point.')
        backup = backups/(path.name+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        path.rename(backup)
        try:
            fresh.rename(path)
        except OSError:
            backup.rename(path)
            raise
        print('Previous ZIP installation preserved:',backup,flush=True)


def compile_nodes(py, nodes, constraint):
    """Run the repositories' own installers in the active portable environment."""
    env = os.environ.copy()
    env['COMFY_PYTHON'] = str(py.resolve())
    env['PIP_CONSTRAINT'] = env['UV_CONSTRAINT'] = str(constraint.resolve())
    env['PATH'] = str(py.parent/'Scripts') + os.pathsep + env.get('PATH', '')
    for path in nodes:
        if not (path/'install_requirements.bat').is_file():
            raise RuntimeError('Missing node installer: '+str(path/'install_requirements.bat'))
    for path in nodes:
        print('Checking build prerequisites:',path.name,flush=True)
        subprocess.run(['cmd.exe','/d','/c','call install_requirements.bat --check'],
                       cwd=path,env=env,check=True)
    print('ComfyUI will stay stopped until the entire node group is installed and verified.',flush=True)
    for index,path in enumerate(nodes,1):
        print('Installing and compiling ['+str(index)+'/'+str(len(nodes))+']:',path.name,flush=True)
        try:
            subprocess.run(['cmd.exe','/d','/c','call install_requirements.bat'],
                           cwd=path,env=env,check=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError('Installation failed for '+path.name+
                               '. See the build error above; the group is not marked installed.') from error
    wtivo = next(path for path in nodes if path.name=='ComfyUI-WTiVo-WatertightVoxel-AMD')
    subprocess.run([str(py),str(wtivo/'wtivo.py'),'--help'],cwd=wtivo,env=env,check=True)
    subprocess.run([str(py),'-c',
                    'import cumesh._C, cumesh._cubvh, cumesh._xatlas, o_voxel._C, trellis2'],
                   env=env,check=True)


def main(group):
    root = Path(__file__).resolve().parent.parent
    py = root/'python_embeded/python.exe'
    collection = json.loads((root/'amd/wtivo-node-groups.json').read_text())[group]
    if group=='boomercyb':
        import torch
        name = torch.cuda.get_device_name() if torch.cuda.is_available() else ''
        if not torch.version.hip or 'RX 9070 XT' not in name.upper() or not torch.__version__.startswith('2.15.0a0+rocm10.2'):
            raise RuntimeError('BoomerCyb nodes require RX 9070 XT and the PyTorch 2.15 / ROCm 10.2 custom-node bundle. Select that preset in ROCm Bundle Manager first.')
    marker = root/'amd'/('wtivo-'+group+'-installed.json')
    marker.unlink(missing_ok=True)
    constraint = root/'amd/amd-constraints.txt'
    constraints(py,constraint)
    os.environ['PIP_CONSTRAINT'] = os.environ['UV_CONSTRAINT'] = str(constraint)
    installed = []
    for name in collection['nodes']:
        path = root/'ComfyUI/custom_nodes'/name
        if not path.resolve().is_relative_to((root/'ComfyUI/custom_nodes').resolve()):
            raise ValueError('Invalid custom-node path')
        update_node(root,path,'https://github.com/'+collection['owner']+'/'+name+'.git')
        for filename in ('requirements-runtime.txt','requirements.txt'):
            requirements = path/filename
            if requirements.is_file():
                install_requirements(py,requirements)
        installed.append(path)
    if group=='boomercyb':
        pip(py,'install','numpy','trimesh','safetensors','tqdm','pymeshlab','Pillow')
        compile_nodes(py,installed,constraint)
    report = dict(group=group,nodes=[path.name for path in installed],complete=True,
                  native_verified=group=='boomercyb')
    marker.write_text(json.dumps(report,indent=2))
    print(collection['label']+' installed. Restart ComfyUI.',flush=True)
    print('Model weights and Blender are installed separately.')
    if group=='mostaadtech':
        print('LODsmith and LODTailor require Blender on PATH or a blender_path in the workflow. FastMerge is CPU-only; Memory Cleaner uses the active PyTorch memory backend.')


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('group',choices=tuple(json.loads((Path(__file__).parent/'wtivo-node-groups.json').read_text())))
    main(parser.parse_args().group)
