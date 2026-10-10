"""Install public PixelArtistry Watertight Meshes workflows, preserving existing files."""
import argparse
import io
import json
from pathlib import Path
from urllib.parse import quote
import zipfile
from download_pixaroma import fetch, install_archive

REPOSITORY = 'pixelartistry/PixelArtistry-Watertight-Meshes'


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
    destination = root/'ComfyUI/user/default/workflows/PixelArtistry'
    # Only workflows not on disk yet are downloaded; existing files are kept as they are.
    missing = [item for item in entries if not destination.joinpath(*item['path'].split('/')[1:]).exists()]
    payload = io.BytesIO()
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED) as archive:
        for item in missing:
            url = 'https://raw.githubusercontent.com/'+REPOSITORY+'/'+commit+'/'+quote(item['path'],safe='/')
            archive.writestr(item['path'][len('workflows/'):],fetch(url))
    stats = {'added':0,'existing':0}
    if missing and install_archive(payload.getvalue(),destination,root/'amd/pixelartistry-backups',stats)!=len(missing):
        raise RuntimeError('Some published files were not valid ComfyUI workflows')
    stats['existing'] += len(entries)-len(missing)
    count = len(entries)
    (root/'amd').mkdir(parents=True,exist_ok=True)
    report = dict(repository=REPOSITORY,commit=commit,complete=True,workflows=count,**stats)
    (root/'amd/pixelartistry-workflows.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'PixelArtistry: {stats["added"]} new, {stats["existing"]} already installed; {count} workflows in {destination}')
    print('Models and custom nodes are installed separately.')


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    main(parser.parse_args().root)
