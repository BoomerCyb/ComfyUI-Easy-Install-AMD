"""Download public Pixaroma episode ZIPs and install their ComfyUI JSON workflows."""
import argparse
from datetime import datetime
import io
import json
from pathlib import Path, PurePosixPath
import re
import time
from urllib.parse import quote, urljoin, urlparse
from urllib.request import urlopen
import zipfile

SITE = 'https://workflows.pixaroma.com/'


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


def catalog(data):
    text = data.decode('utf-8-sig')
    match = re.search(r'window\.EPISODES\s*=\s*',text)
    if not match:
        raise ValueError('Pixaroma catalog format changed')
    episodes,_ = json.JSONDecoder().raw_decode(text[match.end():])
    if not isinstance(episodes,list):
        raise ValueError('Invalid episode catalog')
    return episodes


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
    destination = root/'ComfyUI/user/default/workflows/Pixaroma'
    backup = root/'amd/pixaroma-backups'/datetime.now().strftime('%Y%m%d-%H%M%S')
    report = {'source':SITE,'destination':str(destination),'workflows':0,'added':0,'existing':0,'episodes':[],'failures':[]}
    episodes = catalog(fetch(urljoin(SITE,'episodes.js')))
    for episode in sorted(episodes,key=lambda item:int(item['number'])):
        download = episode.get('downloadPath')
        if not download or episode.get('workflowCount') == 0:
            continue
        number = int(episode['number'])
        url = urljoin(SITE,quote(download,safe='/'))
        if urlparse(url).netloc!=urlparse(SITE).netloc:
            raise ValueError('Unexpected download host')
        try:
            stats = {'added':0,'existing':0}
            count = install_archive(fetch(url),destination/f'Ep{number:02d}',backup/f'Ep{number:02d}',stats)
            if count==0:
                raise ValueError('No ComfyUI JSON workflows in archive')
            report['workflows']+=count
            report['added']+=stats['added']
            report['existing']+=stats['existing']
            report['episodes'].append(number)
            print(f'Episode {number}: {stats["added"]} new, {stats["existing"]} already installed',flush=True)
        except (OSError,ValueError,zipfile.BadZipFile) as error:
            report['failures'].append({'episode':number,'error':str(error)})
            print(f'Episode {number}: unavailable or failed: {error}',flush=True)
    report['complete'] = bool(report['workflows']) and not report['failures']
    (root/'amd').mkdir(parents=True,exist_ok=True)
    (root/'amd/pixaroma-workflows.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'Added {report["added"]} workflows; retained {report["existing"]} existing workflows in {destination}',flush=True)
    print('Required custom nodes and models are downloaded separately. NVIDIA-specific workflows may need AMD changes.')
    if not report['complete']:
        raise RuntimeError('Some downloads failed. Installed workflows were retained; run again to retry.')


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    main(parser.parse_args().root)
