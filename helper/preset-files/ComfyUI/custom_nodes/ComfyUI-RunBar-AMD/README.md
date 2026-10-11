# Run Bar Monitor (AMD)

Puts a run timer, a memory readout and three memory buttons in ComfyUI's top bar, next to **Run**, so they are there in every workflow without adding nodes:

- **Timer**: counts up while a workflow runs and keeps the last run's time afterwards.
- **VRAM / Peak / RAM / CPU**: VRAM used and total, the highest VRAM reached during the current run (it resets when you press Run), RAM and CPU use. It updates every second, three times a second while a workflow runs.
- **Free VRAM**: unloads the models and clears the node cache.
- **Unload**: unloads the models but keeps the node cache, so a rerun does not recompute the parts that did not change.
- **Reset Peak**: clears the peak mark.

The readout uses the Pixaroma monitor feed when ComfyUI-Pixaroma is installed, and ComfyUI's own system stats otherwise (VRAM and RAM, no CPU). The buttons use ComfyUI's own `/free` route, the one behind its "Free model and node cache" menu entry.

## Install

Easy Install adds it to `ComfyUI/custom_nodes` for you. By hand: copy the `ComfyUI-RunBar-AMD` folder into `ComfyUI/custom_nodes`, restart ComfyUI, then reload the browser. No requirements and no nodes.

To hide it, open **Settings**, search for **Run Bar**, and switch it off. To uninstall, remove this folder and restart ComfyUI.

Needs a ComfyUI frontend with action bar buttons (1.33 or newer).
