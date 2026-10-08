"""Keep the mutually exclusive augmentation providers consistent across nodes."""
from pathlib import Path
import re
import tempfile
from bundles import pip

VISION_REQUIREMENTS = ('albumentations==2.0.8','albucore==0.0.24')


def install_requirements(py, path):
    path = Path(path)
    text = path.read_text(encoding='utf-8-sig')
    normalized = re.sub(r'(?im)^\s*albumentationsx(?:\[[^\]]*\])?(?:[^\r\n]*)$',
                        VISION_REQUIREMENTS[0],text)
    if normalized == text:
        return pip(py,'install','-r',str(path))
    print('Using the shared Albumentations 2.0.8 provider for',path.parent.name,flush=True)
    # Retain relative requirements paths without modifying the upstream Git file.
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.txt',prefix='.amd-requirements-',
                                     dir=path.parent,delete=False) as temporary:
        temporary.write(normalized+'\n'+VISION_REQUIREMENTS[1]+'\n')
        adjusted = Path(temporary.name)
    try:
        pip(py,'install','-r',str(adjusted))
    finally:
        adjusted.unlink(missing_ok=True)
