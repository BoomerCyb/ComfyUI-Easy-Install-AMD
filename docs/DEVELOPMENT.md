# Working on the installer

## Branches

- `source`: the installer's code (`helper/`, `tools/`, `docs/`, CI). All pull requests go here.
- `Windows` (default): only what users need - `ComfyUI-Easy-Install-AMD.bat`, `Helper-CEI.zip`,
  `README.md`, `LICENSE`. The installer installs into the folder it runs from, so a clone or
  Download ZIP of this branch must not contain the source. Never merge `source` into `Windows`;
  copy the files with `tools/sync_windows.py` (see Releasing).

## Changing the installer

The installer's code lives in `helper/`. `Helper-CEI.zip` is generated from it and stays committed, because
`ComfyUI-Easy-Install-AMD.bat` extracts it during installation.

1. Edit files under `helper/` (for example `helper/amd/setup.py`).
2. Rebuild the ZIP: `python tools/build_release.py`
3. Commit the `helper/` changes together with the rebuilt `Helper-CEI.zip`, and open the pull request
   against `source`.

`python tools/build_release.py --check` fails when the ZIP and `helper/` differ; GitHub Actions runs it
on every push and pull request.

The build adds `amd/helper-manifest.json` to `Helper-CEI.zip`: the release version and the SHA-256 of
every shipped file. `Update Easy-Install.bat` (`helper/amd/self_update.py`) uses it to tell files a user
edited from shipped ones. Bump `APP_VERSION` in `ComfyUI-EZi.py` and `VERSION` in
`ComfyUI-EZi-Launcher.py` together for each release; the build stops if they differ.

Batch files must use CRLF line endings; the build stops on a `.bat` with LF-only lines.

## Releasing

1. On `source`: `python tools/build_release.py --release` writes `dist/ComfyUI-Easy-Install-AMD.zip`.
2. Update `Windows`:

       git worktree add ../ezi-windows Windows
       python tools/sync_windows.py ../ezi-windows

   Commit there and open a pull request into `Windows`.
3. Create the GitHub release on `Windows` with `dist/ComfyUI-Easy-Install-AMD.zip` attached.

The updater installs the latest GitHub release, so publish a release as "latest" only when it is ready.
