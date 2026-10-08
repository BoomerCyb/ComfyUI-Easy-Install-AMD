"""Run the ROCm CLI using this Python, independent of pip launcher paths."""
from importlib.metadata import entry_points
import sys

if __name__ == '__main__':
    cli = next((entry for entry in entry_points(group='console_scripts')
                if entry.name == 'rocm-sdk'), None)
    if cli is None:
        raise RuntimeError('ROCm SDK is not installed in this Python bundle')
    sys.argv[0] = 'rocm-sdk'
    raise SystemExit(cli.load()())
