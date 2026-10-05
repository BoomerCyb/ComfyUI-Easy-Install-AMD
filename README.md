<p align="center">🌍 <strong>English</strong></p>

---

<div align="center">
  <img src="docs/EZi-Logo.svg" width="120" alt="EZi Logo">
  <h1>ComfyUI-Easy-Install-AMD</h1>
  <p align="center">
    <strong>One-click Portable ComfyUI with EZi Desktop: a full dashboard for packages, environments and configuration</strong><br />
    Windows • AMD GPUs • Pixaroma Community Edition
  </p>

[![GitHub Release](https://img.shields.io/github/v/release/BoomerCyb/ComfyUI-Easy-Install-AMD)](https://github.com/BoomerCyb/ComfyUI-Easy-Install-AMD/releases/latest/download/ComfyUI-Easy-Install-AMD.zip)
[![GitHub Release Date](https://img.shields.io/github/release-date/BoomerCyb/ComfyUI-Easy-Install-AMD?style=flat&label=date)](https://github.com/BoomerCyb/ComfyUI-Easy-Install-AMD/releases)
[![Downloads](https://img.shields.io/github/downloads/BoomerCyb/ComfyUI-Easy-Install-AMD/total)](https://github.com/BoomerCyb/ComfyUI-Easy-Install-AMD/releases)



  <p align="center">
    <a href="#%EF%B8%8F-windows-installation">📥 Install</a> &nbsp;·&nbsp;
    <a href="#-features">✨ Features/Components</a> &nbsp;·&nbsp;
    <a href="https://github.com/Tavris1/ComfyUI-Easy-Install/tree/MAC-Linux">🍎 Upstream macOS/Linux</a> &nbsp;·&nbsp;
    <a href="https://discord.gg/gggpkVgBf3">💬 Pixaroma Discord</a> &nbsp;·&nbsp;
    <a href="#%EF%B8%8F-support-development">❤️ Support Development</a>
  </p>

<!-- Dedicated to the **Pixaroma** community  
[![Dynamic JSON Badge](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fdiscord.com%2Fapi%2Finvites%2FgggpkVgBf3%3Fwith_counts%3Dtrue&query=%24.approximate_member_count&logo=discord&logoColor=white&label=Pixaroma%20Discord&color=FFDF00&suffix=%20users)](https://discord.com/invite/gggpkVgBf3)
-->

</br>

![ComfyUI Screenshot](docs/ComfyUI-ivo.png)

</div>

## ✨ Features

**ComfyUI-Easy-Install-AMD** provides a portable ComfyUI environment with **EZi Desktop**.  
No manual Python or Git setup required.

Install AMD-compatible packages such as Nunchaku-AMD, SageAttention, FlashAttention, InsightFace, and others with one click.

Manage **models, packages, PyTorch/ROCm versions, Dynamic VRAM,  
ComfyUI/frontend versions, UV/PIP caches, and GGUF conversion** from one place.

## 📦 Included Components
<details open>
<summary><b>Core Components</b></summary>

| 🔧 Component | 📝 Note |
|---|---|
| [Git](https://git-scm.com/) | ![Git version](https://img.shields.io/github/v/tag/git/git?label=&display_name=tag&color=blue) - Latest (will install/update if needed) |
| [Python](https://www.python.org/downloads/release/python-31210/) | ![Python version](https://img.shields.io/badge/3.12.10-blue) - Embedded version |
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI) | Official ComfyUI with AMD/ROCm setup |

</details>

<details>
<summary><b>Nodes Used in Pixaroma Tutorials</b></summary>

| 🖼️ Image | 🎬 Video | 🎵 Audio | 🧩 Utility / WF | 🤖 Models |
|---|---|---|---|---|
| [Tiled Diffusion & VAE](https://github.com/shiimizu/ComfyUI-TiledDiffusion) | [VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | [MelBandRoFormer](https://github.com/kijai/ComfyUI-MelBandRoFormer) | [ComfyUI Manager](https://github.com/Comfy-Org/ComfyUI-Manager) | [QwenVL](https://github.com/1038lab/ComfyUI-QwenVL) |
| [Inpaint CropAndStitch](https://github.com/lquesada/ComfyUI-Inpaint-CropAndStitch) | [WanVideoWrapper](https://github.com/kijai/ComfyUI-WanVideoWrapper) | [Qwen3-TTS](https://github.com/flybirdxx/ComfyUI-Qwen-TTS) | [Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use) | [GGUF](https://github.com/city96/ComfyUI-GGUF) |
| [ControlNet Aux](https://github.com/Fannovel16/comfyui_controlnet_aux) | [WanAnimatePreprocess](https://github.com/kijai/ComfyUI-WanAnimatePreprocess) | | [KJNodes](https://github.com/kijai/ComfyUI-KJNodes) | |
| [LayerStyle](https://github.com/chflame163/ComfyUI_LayerStyle) | [SeedVR2 VideoUpscaler](https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler) | | [rgthree](https://github.com/rgthree/rgthree-comfy) | |
| [RMBG](https://github.com/1038lab/ComfyUI-RMBG) | | | [iTools](https://github.com/MohammadAboulEla/ComfyUI-iTools) | |
| [Easy-Sam3](https://github.com/yolain/ComfyUI-Easy-Sam3) | | | [ControlAltAI Nodes](https://github.com/gseth/ControlAltAI-Nodes) | |
| [SCAIL-Pose](https://github.com/kijai/ComfyUI-SCAIL-Pose) | | | ✨[Pixaroma](https://github.com/pixaroma/ComfyUI-Pixaroma) | |
| | | | [Krea2T-Enhancer](https://github.com/capitan01R/ComfyUI-Krea2T-Enhancer) | |
| | | | [Krea2Edit](https://github.com/lbouaraba/comfyui-krea2edit) | |

</details>

<details>
<summary><b>Optional Add-ons & Tools</b></summary>

| 🧩 Nodes | 🛠️ Tools |
|---|---|
| [Nunchaku-AMD — RX 9070 XT only](https://github.com/BoomerCyb/Nunchaku-AMD) | Easy-Models-Linker |
| [SageAttention ROCm](https://github.com/Comfy-Org/ComfyUI) | Easy-System-Checker |
| [FlashAttention / AITER ROCm](https://github.com/Comfy-Org/ComfyUI) | ROCm Bundle Manager |
| [InsightFace](https://github.com/deepinsight/insightface) | Easy-model2GGUF |
| [BoomerCyb WTiVo AMD Nodes](https://github.com/BoomerCyb) | Long-Paths-Enabler |
| [MostAadTech WTiVo Nodes](https://github.com/Mstafa-awad) | Pixaroma / PixelArtistry workflows |
| | Torch-Pack |
| | Toggle-DynamicVRAM |
| | Update Easy-Install |

</details>

---

## 🖥️ Windows Installation

The installer detects your AMD GPU and downloads the matching ROCm packages.
Nunchaku-AMD model loaders support **RX 9070 XT only**. Other GPUs and optional
add-ons have different compatibility requirements. Internet access is required.

> [!WARNING]
> **Windows 11:** If ComfyUI shows **"Bad Image" (`0xc0e90002`)**, turn off **Smart App Control** and restart ComfyUI.<br>
> This reduces protection against untrusted apps. Read the Windows warning before confirming.

> [!IMPORTANT]
> - Do not run the installer as **Administrator**.
> - Avoid system folders (`Program Files`, `Windows`, `C:\` root).
> - Avoid spaces and special characters in folder names.
> - Make sure your AMD drivers are up to date.

1. [**📥 DOWNLOAD LATEST VERSION**](https://github.com/BoomerCyb/ComfyUI-Easy-Install-AMD/releases/latest/download/ComfyUI-Easy-Install-AMD.zip)

The installer uses the folder containing `ComfyUI-Easy-Install-AMD.bat` directly. GitHub's default `ComfyUI-Easy-Install-AMD-Windows` folder is renamed to `ComfyUI-Easy-Install-AMD` before setup; custom folder names are preserved, and an existing destination is never overwritten. After successful installation it removes that setup batch, `Helper-CEI.zip`, and the supplied root README, LICENSE and docs files. License notices and documentation remain under `documentation`; changed or additional user files are preserved. Use `ComfyUI-Easy-Install-AMD Launcher.bat` afterward.
2. Extract the entire ZIP file to a new folder, keeping **`Helper-CEI.zip`** beside the installer, and run **`ComfyUI-Easy-Install-AMD.bat`**
3. Optionally, after the setup, install or run components from the **Add-ons** folder or **EZi Desktop Menu**:
    - **Easy-Models-Linker** - *Uses existing **MODELS** folder via **extra_model_paths.yaml**, no re-download needed*
      - *Some folders like **LLM** and **llm_gguf** cannot be redirected this way*
    - **Easy-System-Checker** - *Provides information about key hardware and software components*
    - **Nunchaku-AMD** - *Downloads our separate RX 9070 XT add-on, including Qwen-Image 2.1 and Viggle 6-step Turbo; model downloads are separate*
    - **SageAttention** - *Installs the matching AMD/ROCm attention package*
    - **FlashAttention** - *Installs compatible ROCm FlashAttention/AITER packages for the selected bundle*
    - **InsightFace** - *Installs InsightFace*
    - **BoomerCyb WTiVo AMD Nodes** - *Installs the five custom AMD mesh nodes and runs each node's install batch to build its native backends with ComfyUI's Python. Requires the matching HIP SDK, Visual Studio C++ Build Tools/Windows SDK, and WTiVo's vcpkg CPU dependencies. Installed appears after backend verification succeeds.*
    - **MostAadTech WTiVo Nodes** - *Installs four mesh and memory utilities; Blender is required for the Blender-based nodes*
    - **Pixaroma Workflows** - *Downloads workflows and checks for new ones*
    - **PixelArtistry Workflows** - *Downloads the watertight workflows*
    - **Torch-Pack / ROCm Bundle Manager** - *Choose precompiled stable PyTorch/ROCm presets, the RX 9070 XT custom-node bundle, advanced versions, or restore a saved environment*
    - **Easy-model2GGUF** - *Convert & quantize models to GGUF (Q2_K–Q8_0) with 5D tensor fixes if available*
    - **Long-Paths-Enabler** - *Enables **Long Paths** in Windows 10/11. Essential for Python/ComfyUI*
    - **ComfyUI Version Controls** - *Official Comfy-Org updates and frontend selection*
    - **Toggle-DynamicVRAM** - *Toggles **--disable-dynamic-vram** option in ComfyUI startup files*
    - **Update Easy-Install** - *Use releases from this AMD fork; the original NVIDIA helper updater is disabled*
    - **EZi Desktop Themes** - *via EZi Desktop > Menu > Advanced*
    - **Custom Input, Output & User folders** - *via EZi Desktop > Menu > Advanced*
    - **ComfyUI & Frontend Version Changer** - *via EZi Desktop > Menu > Advanced*
    - **UV & PIP cache cleaner** - *via EZi Desktop > Menu*
    - **ComfyUI-Manager Security-Level Config** - *Easy configuration of security_level via EZi Desktop > Menu*
    - **Pinned-Packages-Manager** - *Freeze package versions such as NumPy==1.26.4 via EZi Desktop > Menu*

<div align="center">

---

## ❤️ Support Development

Original Easy Install by **ivo / Tavris1**. AMD/ROCm integration adapted from
**patientx**. This is a modified AMD edition. Original author support links:

Enjoy the original project? Your support helps keep it going.

[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/tavris1)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/tavris1)
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-30363D?style=for-the-badge&logo=GitHub-Sponsors&logoColor=#white)](https://github.com/sponsors/Tavris1)

</div>

### AMD Edition Changes - 2026-10-03

Node add-on installers update existing clean Git checkouts before setup. ZIP-installed WTiVo nodes are backed up outside `custom_nodes` before replacement. Nunchaku downloads the current fork with a backup of the previous copy. Update Nodes also runs each node's install batch or Python installer after updating requirements; local source edits stop updates instead of being overwritten.

Modified by **BoomerCyb** from **ivo/Tavris1’s ComfyUI-Easy-Install**, with ROCm integration adapted from **patientx**.

- Added AMD GPU detection, ROCm bundle management, and AMD-compatible add-ons.
- Retained EZi Desktop and the original installer layout.
- Nunchaku-AMD downloads from its separate repository.

Original credits and license notices are preserved.

Upstream sources:

- [ComfyUI-Easy-Install](https://github.com/Tavris1/ComfyUI-Easy-Install), Windows revision `7bd6b5be3254e3134fd2e21c95f0a312e4d3fd96`.
- [ComfyUI](https://github.com/Comfy-Org/ComfyUI), downloaded from its official master branch. GPU mappings and ROCm setup are adapted from patientx; original credits remain in LICENSE.
- [Nunchaku-AMD](https://github.com/BoomerCyb/Nunchaku-AMD), downloaded separately; its `NOTICE*.txt` files document adapter sources and checkpoint revisions.

Modified setup and launcher source is included inside `Helper-CEI.zip`.
The combined AMD installer is GPL-3.0; original Easy Install components retain
their MIT terms. Both notices are preserved in `LICENSE`. Downloaded models
retain their own licenses. This AMD edition is independent of the upstream authors.

### Offline 3D previews - 2026-10-04

Setup and Update ComfyUI install a small local extension that allows browser-local `blob:` texture loading in offline mode. Embedded GLB textures display in core and custom preview nodes while external connections remain blocked. ComfyUI source files remain unchanged, so updates preserve this fix. Restart ComfyUI after updating.

### ComfyUI Shape - 2026-10-04

ComfyUI Shape is included automatically in fresh installs. Open Settings, search for **Node shape**, and choose **Box** (square corners, default) or **Card** under **ComfyUI Shape**. The selection is remembered and applies to existing nodes, new nodes, and loaded workflows. No GPU build or extra requirements are needed. Update ComfyUI also restores the bundled extension; restart ComfyUI and reload the browser afterward.

### Triton and optional attention packages - 2026-10-04

Triton installs automatically with the core GPU bundle so bundled Triton-dependent nodes can load. There is no separate Triton add-on button. Sage Attention and Flash Attention remain optional Add-ons. The regular launcher keeps the ComfyUI Triton backend disabled and uses PyTorch attention; custom nodes may still use Triton internally.

### Official ComfyUI transition

Fresh installations clone official **Comfy-Org/ComfyUI**. Updates, release checks, tag lists and requirements lookups also use the official repository. Existing patientx installations are not switched in place: use a fresh folder and preserve models, workflows, input and output. The normal launcher explicitly selects PyTorch attention; Kitchen, Sage and Flash remain separate launch choices. AMD package management, default Triton and optional Sage/Flash add-ons, ComfyUI Shape, and offline texture previews remain included. This release has not yet been validated with a complete fresh GPU installation. ROCm/PyTorch still default to the nightly channel; ComfUI Default (PyTorch 2.13 / ROCm 10.0), AMD Stable presets, exact nightly versions and saved bundles are available in the Bundle Manager. The separate Latest AMD Nightly button prepares the latest nightly. Opening Bundle Manager keeps ComfyUI running until you close EZi Desktop to activate a prepared bundle.

Add-ons display order: Easy-Models-Linker, FlashAttention AMD, SageAttention AMD, InsightFace, Nunchaku - RX 9070 XT, Pixaroma Workflows, PixelArtistry Watertight Workflows, BoomerCyb WTiVo AMD Nodes, MostAadTech WTiVo Nodes. Easy-Models-Linker does not show an Installed label.

INT8-Fast-ROCM is no longer part of the default node collection. Existing installations are not removed automatically.

Default nodes now match the original Easy Install collection. Removed patientx-setup additions: CFZ-SwitchMenu, CFZ-Caching, HFRemoteVae, H3 SLA Attention ROCm and Spectrum Qwen2.1, alongside INT8-Fast-ROCM. AMD attention package add-ons and their original attribution remain. Existing installed node folders are not deleted automatically.

### System Info

Displays EZI, ComfyUI, Frontend, Python, PyTorch, HIP, ROCm, AMD Drv, GPU Model, Video VRAM, System RAM, Page File and Long Paths. PyTorch includes its full version and the AMD driver is read from Windows. The pinned Triton package still requires AMD kernel compatibility testing with the nightly runtime.
