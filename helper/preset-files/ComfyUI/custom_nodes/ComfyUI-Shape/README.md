# ComfyUI Shape

Choose **Box** or **Card** as the default shape for ComfyUI nodes. Box has square corners; Card uses ComfyUI's built-in card shape. Box is selected by default. Supports the standard classic and Nodes 2.0 renderers. Extensions that draw their own outlines can have their own appearance.

## Install

Extract the `ComfyUI-Shape` folder into `ComfyUI/custom_nodes`, restart ComfyUI, then reload the browser. No requirements installer or GPU compilation is needed.

Open **Settings**, search for **Node shape**, and use the **ComfyUI Shape** Box/Card selector. ComfyUI remembers your choice. Changing it updates the current nodes, including subgraph nodes; new nodes and loaded workflows use the selected shape too.

This frontend extension adds no workflow node and does not change node sizes, connections, or execution. Shapes are saved when you save your workflow. Manual per-node shape changes are possible, but loading a workflow or changing the selector reapplies the selected default.

To uninstall, remove this folder and restart ComfyUI. Shapes already saved in workflows remain as saved.
