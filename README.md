# ComfyUI-Easy-Install-AMD

Experimental Windows AMD/ROCm conversion of Tavris1's Easy Install, retaining
EZi Desktop and using patientx's ComfyUI ROCm fork. Installation and representative full-model generation have been tested on
Windows with an RX 9070 XT. Other AMD cards and NVIDIA numerical parity are unverified.

The runtime uses `.bat` entry points and Python helpers. PowerShell is not required.
Python is bootstrapped with Windows `curl.exe` and `tar.exe`. GPU detection uses
patientx's architecture mappings with WMIC and a native Windows registry fallback.

## Install

Download the release ZIP and extract its ComfyUI-Easy-Install-AMD folder. Run
`ComfyUI-Easy-Install-AMD.bat` as a normal user. From source, first run
`Build Release.bat` with Python 3 installed; release files appear in `dist/`.
The installer creates a separate portable `ComfyUI-Easy-Install-AMD` folder here.
It does not modify another ComfyUI installation.

The installer downloads embedded Python 3.12.10, detects the AMD GPU using
patientx's detector, selects its `gfx` package architecture, and installs AMD's
ROCm/PyTorch packages. RDNA is detected from the hardware; it is not a separate
package to install. Current patientx nightly packages are the default.

After setup, launch `ComfyUI-Easy-Install-AMD/ComfyUI-Easy-Install-AMD Launcher.bat`. The Python folder
remains named `python_embeded`. Both the console launchers and EZi Desktop apply
ROCm initialization and patientx's RDNA-specific attention/environment settings.

The separate EZi Launcher window (Desktop / Browser / Update buttons) opens through
the desktop **ComfyUI-Easy-Install-AMD Launcher** shortcut or the installed
`ComfyUI-Easy-Install-AMD Launcher.bat`. Setup creates the shortcut automatically.
The download ZIP contains one named folder with `ComfyUI-Easy-Install-AMD.bat`,
the README, change/source notes and license texts. Setup clones
this GitHub fork, downloads portable Python, and stages the EZi assets, AMD
helpers and license notices automatically. Release ZIPs pin the helper source
to an exact Git commit. No separate helper ZIP is needed. Running the batch
file directly from source uses the current Windows branch. Internet access is required.

## Included

- EZi Desktop and its separate launcher, console, themes, launch arguments,
  frontend controls, cache tools, pinned packages, custom folders and model linker.
- The complete Easy Install custom-node collection and additional AMD-compatible nodes, workflows, Python
  headers/libraries and GGUF conversion tools. Nodes remain subject to AMD
  compatibility; failures are listed in `amd/node-install-report.json`.
- ComfyUI Manager plus patientx's CFZ-SwitchMenu, CFZ-Caching, HFRemoteVae,
  INT8-Fast-ROCM and H3 SLA attention extensions.
- AMD Triton 3.7.0.post26, SageAttention 2.2, ROCm bitsandbytes, and optional
  ROCm FlashAttention/AITER. gfx1201 selects patientx's native SageAttention wheel.
- InsightFace installer with CPU ONNX Runtime, portable SoX where downloadable,
  and an optional CPU llama-cpp wheel instead of the NVIDIA CUDA wheel.

The **Nunchaku AMD — RX 9070 XT only** add-on installs the full model
loader and the `Nunchaku-AMD-Qwen-Image` workflow. It downloads the original
Nunchaku Qwen-Image INT4 checkpoint, matching Qwen 2.5 text encoder and VAE
if missing (about 21 GB total). Restart ComfyUI, open that workflow and run it.
The initial workflow uses 256 by 256 pixels and 12 Euler steps for a small test.
It uses existing ROCm PyTorch and Triton without changing packages, keeping
compressed blocks in system RAM and moving one block at a time to the GPU.
Allow at least 32 GB of system RAM; larger images and encoder loading need
additional memory. The supported GPU is RX 9070 XT/gfx1201.
For original Qwen-Image, external LoRAs and attention patches are unsupported. INT4 weights
are expanded into BF16/FP16 tiles; this does not use native INT4 matrix instructions.
NVIDIA output equivalence and production performance have not been established.
The separate `Nunchaku-AMD-Qwen-Layer-Test` workflow remains available for diagnosis.
The bundled single-layer fixture and prototype include Apache 2.0 notices.

The add-on now also supports **Qwen-Image 2.1 Nunchaku INT4** through the separate
`Nunchaku-AMD-Qwen-Image-2.1` and `Nunchaku-AMD-Qwen-Image-2.1-Viggle-Turbo`
workflows. Choose model set 2 in the Nunchaku add-on menu. These load the real
Mesmer signed INT4 rank-128 checkpoint, replacing all 224 projection layers
with AMD Triton modules. The compressed transformer uses about 4.65 GB of storage;
the matching encoder, VAE and Turbo adapter bring a fresh download to about 15.4 GB.
Turbo applies Viggle v0.3 as runtime branches and uses its six-step schedule with
Euler and CFG 1. Standard LoRA merging is unsupported. Model files retain their
own Qwen Research License; see the linked model repositories in NOTICE-QWEN21.txt.
On RX 9070 XT, the optimized 512-pixel base test took about 57 seconds and
allocated 6.0 GiB peak VRAM; Turbo took about 6 seconds and allocated 6.6 GiB.
The larger validated Triton tile produced exactly the same full-model benchmark
output as the original tile. Cached unpacked SVD branches trade about 1.3 GiB
extra VRAM for less repeated work. These measurements exclude text encoding
and VAE decode. Base generation remains slower than native BF16.
The `Nunchaku-AMD-Qwen-Image-2.1-Viggle-Turbo-Edit` workflow accepts reference
images. A red-to-blue teapot edit passed at 512 pixels in about 8 seconds.

The add-on also includes real packed INT4 adapters and workflows for
**Z-Image Turbo** (136 projections, 34 blocks) and **FLUX.1 Schnell**
(304 projections, 57 blocks, AWQ modulation). Their 512-pixel generation tests
passed on RX 9070 XT. Choose model set 4 or 5; set 6 downloads all families,
and set 7 installs nodes/workflows without downloading models.
Set 8 downloads Z-Image Turbo E2M1 FP4 with FP8 group scales; set 6 includes it.
Its independent packing checks and full 512-pixel generation passed on RX 9070 XT
(about 22 seconds, 5.45 GiB peak allocated VRAM). This is software FP4 compatibility
using BF16/FP16 compute, not NVIDIA NVFP4 instructions. Use the separate
`Nunchaku-AMD-Z-Image-Turbo-FP4` workflow; INT4 remains the faster tested option.
Z-Image uses its Qwen3-4B encoder; FLUX uses CLIP-L and T5-XXL. Downloads are
pinned, checked, resumable, and separate from the installer ZIP.

Model loaders require RX 9070 XT/gfx1201.
Only gfx1201 has full generation validation; a probe pass on another GPU is
not equivalent to that validation. The fast 64x64 tile defaults only on gfx1201;
other GPUs retain the conservative tile. `NUNCHAKU_GEMM_TILE=16,32` forces it.
NVIDIA extension compatibility, arbitrary LoRA merging and original Qwen Edit
are unsupported. Other families' FP4 checkpoints, FLUX dev/Kontext and other Z-Image
variants have not been validated. Quality examples cover three matched prompts;
they do not establish universal quality equivalence or improvement.

The add-on also includes FLUX.2 Klein 9B, SDXL, SANA, a quantized T5 encoder
for FLUX.1, and LTX-2.3 distilled video/audio. Choose A/B/C/D/E respectively
in `Add-Ons/Nunchaku.bat`, or 6 for all model bundles. Downloads use pinned
revisions and remain separate from the installer ZIP. Restart ComfyUI after
installing the nodes and open the matching `Nunchaku-AMD-*` workflow.

All eight families have full generation tests on RX 9070 XT/gfx1201 with
representative INT4 checkpoints. LTX generated nine frames at 256x256 with
audio using eight steps and 9.36 GiB peak allocated VRAM. Its transformer
blocks stream from CPU; its encoder/connectors use separate weight-only NF4
dependencies. SANA and LTX use complete pipeline nodes; the other new loaders
connect to standard ComfyUI sampling nodes. T5 was tested through FLUX.1
generation, rather than only a standalone encoding operation.

NVIDIA numerical parity remains unverified. Family coverage does not establish
support for every checkpoint, precision, LoRA, ControlNet or attention patch.
Only Z-Image FP4 has full generation coverage; generic FP4 paths elsewhere
remain experimental. LTX resolutions and clip lengths beyond the small test
require additional memory and have not been validated.

SageAttention 3 and the bundled Trellis2/Pixal3D NVIDIA builds remain unavailable.

## Switch PyTorch / ROCm bundles

In EZi Desktop's Torch section, choose **PyTorch / ROCm Bundle Manager**, or run
`Add-Ons/Torch-Pack/ROCm Bundle Manager.bat` in the installed folder.

The manager supports:

1. Building the current patientx AMD nightly bundle for the detected GPU.
2. Requesting exact Torch, torchvision, torchaudio and ROCm SDK package versions
   available in AMD's index for that GPU. Blank fields use the available latest
   builds. Unavailable or inconsistent versions fail without changing the active
   environment. CUDA versions such as cu128/cu130 are not choices on AMD.
3. Restoring any previously saved complete Python environment.

New bundles are built in separate directories and must pass a ROCm tensor test.
The manager then asks you to close EZi Desktop and this installation's Python
processes before activation. It saves the previous environment for rollback.
Each switch can temporarily require several copies of Python and its packages;
allow substantial disk space. Saved bundles also retain custom-node dependencies.

The tensor test validates ROCm/PyTorch GPU access, not every attention kernel,
custom node, model or workflow. Specific bundle combinations need generation
testing before being described as fully compatible.

## Updates and limitations

ComfyUI updates pull the patientx master branch, preserving the ROCm fork. Package
constraints protect the selected Torch/ROCm stack during dependency installs.
Conflicting node requirements are reported, not silently substituted with CUDA
or CPU PyTorch. Custom installers can ignore package constraints, so setup runs
another GPU check at the end.

ONNX 1.17.0 and protobuf 4.25.8 are pinned to Windows binary wheels. The optional
audio-codec installation is separate: descript-audiotools 0.7.2 requires
protobuf<3.20, which conflicts with this ONNX stack. Its failure is recorded in
the installation report without blocking the base ComfyUI environment.

Original ComfyUI release-tag switching is disabled because those tags can remove
patientx's ROCm changes. Frontend switching remains available. The original Easy
Install helper updater is also disabled because it would overwrite AMD changes;
converted helper updates must come from this AMD project.

The NVIDIA entry point and inherited release automation were removed from
this branch. Use `ComfyUI-Easy-Install-AMD.bat`; `vendor/` preserves license texts.

## Easy Install AMD edition presentation

Easy Menu / Add-ons appends `(Installed)` based on the portable environment's
package metadata and installed node files. Nunchaku's label refers to the node
add-on; its model downloads remain separate. The status refreshes when opening
the menu or returning to the Add-ons tab.

Easy Menu / Torch Pack / ROCm Bundle Manager lists AMD's precompiled stable
PyTorch 2.11, 2.12 and 2.13 / ROCm 10.0 presets, plus the exact RX 9070 XT
custom-node working stack captured on October 3, 2026. Published Windows wheel
metadata was inspected for the stable sets; they have not received the full
Nunchaku hardware tests used for the custom-node stack. Preparation verifies
GPU execution before activation. ROCm 10.2-specific optional binary add-ons
are excluded from stable presets. Nightly and manual versions remain advanced
options. Saved complete environments provide rollback and local restoration.

The installer retains the original Easy Install power logo and EZi Desktop
identity. Setup shows seven named sections, then offers to open the EZi
Launcher. The launcher keeps its Desktop / Browser / Update layout; EZi's
Easy Menu keeps add-ons and the PyTorch / ROCm Bundle Manager in the same flow.
The portable folder and desktop shortcuts remain `ComfyUI-Easy-Install-AMD`.
This is a modified Easy Install edition, with AMD detection and ROCm package
routing underneath the existing EZi interface.

## Validation performed

- Revised GPU detector tested on the local RX 9070 XT: selected `gfx1201` while
  integrated Radeon graphics were also present.
- Twenty-eight automated checks passed for AMD package routing, unsupported architectures,
  launch argument parsing, attention selection, constraint handling, source
  syntax, retained nodes, and removal of CUDA installers.
- No PowerShell calls or `.ps1` files remain in the runtime payload. Bundle activation
  was tested with temporary environments; EZi's inline JavaScript parsed successfully.
- The user confirmed installation, EZi rendering and WTiVo AMD generation.
  The experimental Nunchaku loader passed a full 60-block forward test and
  prompted Qwen-Image generation on the local RX 9070 XT. Live bundle switching
  and broad compatibility across GPUs and add-ons remain untested.

A separate embedded-Python smoke test successfully built and imported a small
source package after installing setuptools/wheel/packaging and disabling pip build
isolation. This confirms the build-backend fix, not the complete ROCm installation.
The test Python lives under `tests/embedded-smoke` and is excluded from the ZIP.

See `UPSTREAM.md` for source revisions and license notices.
