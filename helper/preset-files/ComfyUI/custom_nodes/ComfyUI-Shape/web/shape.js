import { app } from "../../scripts/app.js";

const SETTING_ID = "ComfyUIShape.NodeShape";

function selectedShape() {
    const selected = app.ui.settings.getSettingValue(SETTING_ID, "Box");
    return selected === "Card"
        ? (globalThis.LiteGraph?.CARD_SHAPE ?? 4)
        : (globalThis.LiteGraph?.BOX_SHAPE ?? 1);
}

function applyGraph(graph, shape, visited = new Set()) {
    if (!graph || visited.has(graph)) return;
    visited.add(graph);
    for (const node of graph._nodes ?? []) {
        node.shape = shape;
        if (node.subgraph) applyGraph(node.subgraph, shape, visited);
    }
}

function applyNode(node) {
    if (!node) return;
    const shape = selectedShape();
    node.shape = shape;
    if (node.subgraph) applyGraph(node.subgraph, shape);
}

function refreshGraph() {
    const shape = selectedShape();
    if (globalThis.LiteGraph) globalThis.LiteGraph.NODE_DEFAULT_SHAPE = shape;
    applyGraph(app.graph, shape);
    app.canvas?.setDirty(true, true);
}

app.registerExtension({
    name: "ComfyUIShape.NodeShapes",
    settings: [{
        id: SETTING_ID,
        name: "Node shape",
        category: ["ComfyUI Shape", "Appearance", "Node shape"],
        type: "combo",
        options: ["Box", "Card"],
        defaultValue: "Box",
        tooltip: "Use Box or Card for new nodes and loaded workflows. Changing this also updates the current graph.",
        onChange() {
            // Read the value after ComfyUI finishes storing it.
            queueMicrotask(refreshGraph);
        },
    }],
    setup() { refreshGraph(); },
    nodeCreated(node) {
        applyNode(node);
        queueMicrotask(() => applyNode(node));
    },
    loadedGraphNode(node) { applyNode(node); },
    afterConfigureGraph() { refreshGraph(); },
});
