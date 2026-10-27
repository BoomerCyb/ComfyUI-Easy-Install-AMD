import { app } from "../../scripts/app.js";

const SETTING = "BlankDefaultAMD.Enabled";

// ComfyUI copies its default graph from this one object whenever it needs it (first start, nothing to restore,
// Load Default), so emptying it in place makes every untitled default workflow blank. The original is kept to put
// back when the setting is switched off.
const graph = window.comfyAPI?.defaultGraph?.defaultGraph;
const original = graph ? structuredClone(graph) : null;

function apply(enabled) {
    if (!graph) return;
    for (const key of Object.keys(graph)) delete graph[key];
    Object.assign(graph, structuredClone(enabled ? window.comfyAPI.defaultGraph.blankGraph : original));
}

apply(true); // before the first workflow loads; the setting's value follows in init()

app.registerExtension({
    name: "BlankDefaultAMD",
    settings: [
        {
            id: SETTING,
            category: ["Blank Default Workflow", "Default Workflow", "Blank"],
            name: "Start new and untitled workflows empty instead of ComfyUI's default workflow",
            type: "boolean",
            defaultValue: true,
            onChange: (value) => apply(value !== false),
        },
    ],
    init() {
        apply(app.ui.settings.getSettingValue(SETTING, true) !== false);
    },
});
