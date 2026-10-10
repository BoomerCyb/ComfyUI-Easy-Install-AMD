"""Install public PixelArtistry Watertight Meshes workflows, preserving existing files."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import time
from urllib.parse import quote
from urllib.request import urlopen
import zipfile

REPOSITORY = 'pixelartistry/PixelArtistry-Watertight-Meshes'


def fetch(url):
    for attempt in range(3):
        try:
            with urlopen(url,timeout=60) as response:
                data = response.read(128*1024*1024+1)
                if len(data)>128*1024*1024:
                    raise ValueError('Download exceeds the archive size limit')
                return data
        except OSError:
            if attempt==2:
                raise
            time.sleep(1+attempt)


def install_archive(data, destination, backup, stats=None):
    count = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(item.file_size for item in archive.infolist())>256*1024*1024:
            raise ValueError('Expanded archive exceeds the size limit')
        for item in archive.infolist():
            name = PurePosixPath(item.filename.replace('\\','/'))
            if name.is_absolute() or '..' in name.parts or any(':' in part for part in name.parts):
                raise ValueError('Unsafe archive path')
            if item.is_dir() or name.suffix.lower()!='.json':
                continue
            if item.file_size>64*1024*1024:
                raise ValueError('Workflow exceeds the size limit')
            contents = archive.read(item)
            workflow = json.loads(contents.decode('utf-8-sig'))
            if not isinstance(workflow,dict) or not (
                isinstance(workflow.get('nodes'),list) or
                (workflow and all(isinstance(node,dict) and 'class_type' in node for node in workflow.values()))):
                continue
            target = destination.joinpath(*name.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Workflow escapes destination')
            if target.exists():
                if stats is not None:
                    stats['existing']+=1
                count+=1
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            partial = target.with_suffix('.json.part')
            partial.write_bytes(contents)
            partial.replace(target)
            if stats is not None:
                stats['added']+=1
            count+=1
    return count


def main(root):
    root = root.resolve()
    api = 'https://api.github.com/repos/'+REPOSITORY
    commit = json.loads(fetch(api+'/commits/main'))['sha']
    manifest = json.loads(fetch(api+'/git/trees/'+commit+'?recursive=1'))
    if manifest.get('truncated'):
        raise RuntimeError('GitHub returned an incomplete workflow listing')
    entries = [item for item in manifest['tree'] if item['type']=='blob' and
               item['path'].startswith('workflows/') and item['path'].lower().endswith('.json')]
    if not entries:
        raise RuntimeError('No published workflow JSON files found')
    payload = io.BytesIO()
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED) as archive:
        for item in entries:
            url = 'https://raw.githubusercontent.com/'+REPOSITORY+'/'+commit+'/'+quote(item['path'],safe='/')
            archive.writestr(item['path'][len('workflows/'):],fetch(url))
    destination = root/'ComfyUI/user/default/workflows/PixelArtistry'
    stats = {'added':0,'existing':0}
    count = install_archive(payload.getvalue(),destination,root/'amd/pixelartistry-backups',stats)
    if count!=len(entries):
        raise RuntimeError('Some published files were not valid ComfyUI workflows')
    (root/'amd').mkdir(parents=True,exist_ok=True)
    report = dict(repository=REPOSITORY,commit=commit,complete=True,workflows=count,**stats)
    (root/'amd/pixelartistry-workflows.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'PixelArtistry: {stats["added"]} new, {stats["existing"]} already installed; {count} workflows in {destination}')
    print('Models and custom nodes are installed separately.')


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    main(parser.parse_args().root)
