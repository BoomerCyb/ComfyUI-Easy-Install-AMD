# Working on the installer

The installer's code lives in `helper/`. `Helper-CEI.zip` is generated from it and stays committed, because
`ComfyUI-Easy-Install-AMD.bat` extracts it during installation (also when the repository is downloaded
as source).

1. Edit files under `helper/` (for example `helper/amd/setup.py`).
2. Rebuild the ZIP: `python tools/build_release.py`
3. Commit the `helper/` changes together with the rebuilt `Helper-CEI.zip`.

`python tools/build_release.py --check` fails when the ZIP and `helper/` differ; GitHub Actions runs it
on every push and pull request.

To build a release asset: `python tools/build_release.py --release`, then attach
`dist/ComfyUI-Easy-Install-AMD.zip` to the GitHub release.

Batch files must use CRLF line endings; the build stops on a `.bat` with LF-only lines.
