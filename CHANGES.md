# AMD edition changes — 2026-10-03

Modified by BoomerCyb from Tavris1's Windows Easy Install and patientx's
ROCm integration. This edition adds AMD GPU detection, RDNA bundle selection,
ROCm bundle switching, dependency constraints, AMD launcher integration,
workflow downloads and grouped WTiVo add-ons. Its Nunchaku add-on downloads the separate
Nunchaku-AMD packed-weight ComfyUI adapters from their public repository.

The converted helper files and AMD Python source are inside `Helper-CEI.zip`; the AMD entry point
is `ComfyUI-Easy-Install-AMD.bat`. NVIDIA entry points and inherited release
automation were removed from this branch. Upstream history remains intact.
Original MIT and GPL notices are preserved under `licenses/` and `LICENSE`.

The public layout follows Easy Install: batch installer, helper archive,
README, docs and license notices. No build tools or unpacked helper source
folders are required in the public checkout.
