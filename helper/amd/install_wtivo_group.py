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
import install_lock
import prebuilt_nodes


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


def node_installer(path, *args):
    """cmd.exe line running a node's install_requirements.bat by its full path.

    A string, not a list: list quoting escapes inner quotes for C programs, which
    cmd.exe does not understand. The full path keeps it working when Windows is set
    not to search the current folder (NoDefaultCurrentDirectoryInExePath).
    """
    return ' '.join(['cmd.exe /d /c call "'+str(path.absolute()/'install_requirements.bat')+'"',*args])


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
        subprocess.run(node_installer(path,'--check'),
                       cwd=path,env=env,check=True)
    print('ComfyUI will stay stopped until the entire node group is installed and verified.',flush=True)
    for index,path in enumerate(nodes,1):
        print('Installing and compiling ['+str(index)+'/'+str(len(nodes))+']:',path.name,flush=True)
        try:
            subprocess.run(node_installer(path),
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
        # The nodes compile for the GPUs and PyTorch found here; their own
        # installers check the build prerequisites (compiler, ROCm SDK, headers).
        import torch
        if not torch.version.hip or not torch.cuda.is_available():
            raise RuntimeError('BoomerCyb nodes need ROCm PyTorch with a visible AMD GPU.')
        print('Installing BoomerCyb nodes for', torch.cuda.get_device_name(), 'with PyTorch', torch.__version__,
              '- tested on RX 9070 XT (gfx1201).', flush=True)
        # Prebuilt native modules need the node sources they were built from.
        prebuilt, reason = prebuilt_nodes.find(torch)
    else:
        prebuilt = None
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
        if prebuilt:
            install_lock.checkout(path,prebuilt['nodes'].get(name))
        for filename in ('requirements-runtime.txt','requirements.txt'):
            requirements = path/filename
            if requirements.is_file():
                install_requirements(py,requirements)
        installed.append(path)
    if group=='boomercyb':
        pip(py,'install','numpy','trimesh','safetensors','tqdm','pymeshlab','Pillow')
        used_prebuilt = bool(prebuilt) and prebuilt_nodes.install(root,py,os.environ.copy())
        if not used_prebuilt:
            compile_nodes(py,installed,constraint)
    report = dict(group=group,nodes=[path.name for path in installed],complete=True,
                  native_verified=group=='boomercyb')
    if group=='boomercyb':
        report['prebuilt'] = used_prebuilt
    marker.write_text(json.dumps(report,indent=2))
    print(collection['label']+' installed. Restart ComfyUI.',flush=True)
    print('Model weights and Blender are installed separately.')
    if group=='mostaadtech':
        print('LODsmith and LODTailor require Blender on PATH or a blender_path in the workflow. FastMerge is CPU-only; Memory Cleaner uses the active PyTorch memory backend.')


def rebuild():
    """Recompile the installed native nodes against the active PyTorch (after a bundle switch)."""
    root = Path(__file__).resolve().parent.parent
    py = root/'python_embeded/python.exe'
    marker = root/'amd/wtivo-boomercyb-installed.json'
    if not marker.is_file():
        print('No compiled AMD nodes are installed; nothing to rebuild.',flush=True)
        return
    nodes = [root/'ComfyUI/custom_nodes'/name for name in json.loads(marker.read_text())['nodes']]
    missing = [path.name for path in nodes if not path.is_dir()]
    if missing:
        raise RuntimeError('Installed nodes are missing: '+', '.join(missing)+'. Reinstall the node group.')
    constraint = root/'amd/amd-constraints.txt'
    import torch
    print('Rebuilding compiled AMD nodes for PyTorch', torch.__version__, flush=True)
    prebuilt, _ = prebuilt_nodes.find(torch)
    if prebuilt:
        for path in nodes:
            install_lock.checkout(path,prebuilt['nodes'].get(path.name))
    used_prebuilt = bool(prebuilt) and prebuilt_nodes.install(root,py,os.environ.copy())
    if not used_prebuilt:
        # The node installers keep a build only when it was made for this PyTorch.
        compile_nodes(py,nodes,constraint)
    report = json.loads(marker.read_text())
    report['prebuilt'] = used_prebuilt
    marker.write_text(json.dumps(report,indent=2))
    print('Compiled AMD nodes rebuilt for the active bundle.',flush=True)


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('group',nargs='?',choices=tuple(json.loads((Path(__file__).parent/'wtivo-node-groups.json').read_text())))
    parser.add_argument('--rebuild',action='store_true',help='recompile installed native nodes for the active PyTorch')
    args = parser.parse_args()
    if args.rebuild:
        rebuild()
    elif args.group:
        main(args.group)
    else:
        parser.error('choose a node group or --rebuild')
