"""WTiVo AMD: the BoomerCyb and MostAadTech WTiVo nodes and the PixelArtistry watertight workflows.

Run again at any time: node groups already at the commits an update would install
are skipped, and only workflows not on disk yet are downloaded.
"""
import json
from pathlib import Path

import download_pixelartistry
import install_wtivo_group


def main():
    root = Path(__file__).resolve().parent.parent
    groups = json.loads((root/'amd/wtivo-node-groups.json').read_text())
    for group in ('boomercyb', 'mostaadtech'):
        label = groups[group]['label']
        up_to_date, reason = install_wtivo_group.current(root, group)
        if up_to_date:
            print(label+': up to date.', flush=True)
            continue
        print(label+': '+reason+'; installing.', flush=True)
        install_wtivo_group.main(group)
    download_pixelartistry.main(root)
    print('WTiVo AMD is ready. Model weights and Blender are installed separately.', flush=True)


if __name__ == '__main__':
    main()
