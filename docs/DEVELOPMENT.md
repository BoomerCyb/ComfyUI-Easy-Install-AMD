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

## Tested versions (install lock)

`helper/amd/install-lock.json` holds the ComfyUI commit, each default node's commit and every package
version of a verified installation. New installations reproduce exactly that (`helper/amd/install_lock.py`);
updates still move forward, and `EZI_LATEST=1` installs the newest of everything. Refresh it after a fresh
installation of the release candidate has passed testing:

    python tools/make_install_lock.py D:/path/to/that/installation

## Prebuilt BoomerCyb nodes

`helper/amd/prebuilt.json` lists ZIPs of the BoomerCyb nodes' native modules, built once for every consumer
Radeon architecture of a PyTorch bundle. The BoomerCyb add-on installs them (and moves the nodes to the
commits they were built from) when PyTorch, Python and the GPU match, runs a GPU self-test, and otherwise
compiles from source (`EZI_BUILD_FROM_SOURCE=1` forces that). "Update ComfyUI and Nodes" leaves prebuilt
nodes to the add-on. To build them, on a machine with the build tools and an installation of the default
bundle:

    python tools/build_prebuilt.py D:/path/to/installation --tag nodes-torch<version>-<date>

then upload the ZIP it names to a GitHub release with that tag, not marked latest. Rebuild them when the
default bundle changes or the nodes' native code changes.

## Releasing

1. On `source`: `python tools/build_release.py --release` writes `dist/ComfyUI-Easy-Install-AMD.zip`.
2. Update `Windows`:

       git worktree add ../ezi-windows Windows
       python tools/sync_windows.py ../ezi-windows

   Commit there and open a pull request into `Windows`.
3. Create the GitHub release on `Windows` with `dist/ComfyUI-Easy-Install-AMD.zip` attached.

The updater installs the latest GitHub release, so publish a release as "latest" only when it is ready.
