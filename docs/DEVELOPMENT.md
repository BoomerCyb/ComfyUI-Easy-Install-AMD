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

The build adds `amd/helper-manifest.json` to `Helper-CEI.zip`: the release version and the SHA-256 of
every shipped file. `Update Easy-Install.bat` (`helper/amd/self_update.py`) uses it to tell files a user
edited from shipped ones. Bump `APP_VERSION` in `ComfyUI-EZi.py` and `VERSION` in
`ComfyUI-EZi-Launcher.py` together for each release; the build stops if they differ. The updater
installs the latest GitHub release, so publish a release as "latest" only when it is ready.

Batch files must use CRLF line endings; the build stops on a `.bat` with LF-only lines.
