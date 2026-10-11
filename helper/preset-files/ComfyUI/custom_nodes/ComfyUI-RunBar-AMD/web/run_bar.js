import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const SHOW_SETTING = "RunBarAMD.Show";
const PIXAROMA_STATS = "/pixaroma/api/monitor/stats";
const IDLE_MS = 1000;
const RUNNING_MS = 333; // faster while a workflow runs, so the peak catches the real high point

let peak = 0;
let running = false;
let runStart = null;
let clock = null;
let poll = null;
let usePixaroma = true;

const buttons = {
    timer: { icon: "icon-[lucide--clock]", label: "00:00",
             tooltip: "Run time (live, then the last run)", onClick() {} },
    stats: { icon: "icon-[lucide--cpu]", label: "VRAM -",
             tooltip: "VRAM used / total, peak of this run, RAM, CPU", onClick() {} },
    free: { icon: "icon-[lucide--trash-2]", label: "Free VRAM",
            tooltip: "Free VRAM: unload models and clear the node cache", onClick: () => freeMemory(false) },
    unload: { icon: "icon-[lucide--zap-off]", label: "Unload",
              tooltip: "Unload models (keeps the node cache, reruns stay fast)", onClick: () => freeMemory(true) },
    reset: { icon: "icon-[lucide--rotate-ccw]", label: "Reset Peak",
             tooltip: "Reset the VRAM peak mark", onClick: () => { peak = 0; sample(); } },
};

function buttonElement(button) {
    return document.querySelector(`[data-testid="action-bar-buttons"] button[aria-label="${button.tooltip}"]`);
}

// The action bar does not redraw when a label changes, so the text is set on the
// button too; the stored label keeps it when the bar is drawn again.
function setLabel(button, text) {
    button.label = text;
    const span = buttonElement(button)?.querySelector("span");
    if (span) span.textContent = text;
}

// One style rule hides all five buttons, so it holds however often the bar is drawn.
const hideStyle = document.createElement("style");
hideStyle.textContent = Object.values(buttons)
    .map((button) => `[data-testid="action-bar-buttons"] button[aria-label="${button.tooltip}"]`)
    .join(", ") + " { display: none !important; }";

function applyVisibility() {
    const show = app.ui.settings.getSettingValue(SHOW_SETTING, true);
    if (show) hideStyle.remove();
    else document.head.appendChild(hideStyle);
}

function clockText(seconds) {
    seconds = Math.floor(seconds);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const head = hours ? `${hours}:${String(minutes % 60).padStart(2, "0")}` : String(minutes).padStart(2, "0");
    return `${head}:${String(seconds % 60).padStart(2, "0")}`;
}

const gb = (bytes) => (bytes / 2 ** 30).toFixed(1);

// Pixaroma's monitor feed when it is installed (VRAM, RAM, CPU); ComfyUI's own
// system stats otherwise (VRAM and RAM, no CPU).
async function readStats() {
    if (usePixaroma) {
        try {
            const response = await api.fetchApi(PIXAROMA_STATS);
            if (response.ok) {
                const stats = await response.json();
                const device = stats.devices?.find((d) => d.type !== "cpu") ?? stats.devices?.[0];
                if (device) {
                    return { used: device.used, total: device.total, ram: stats.ram?.pct, cpu: stats.cpu?.pct };
                }
            } else if (response.status === 404) {
                usePixaroma = false;
            }
        } catch {
            usePixaroma = false;
        }
    }
    const stats = await (await api.fetchApi("/system_stats")).json();
    const device = stats.devices?.find((d) => d.type !== "cpu") ?? stats.devices?.[0];
    const system = stats.system ?? {};
    return {
        used: device ? device.vram_total - device.vram_free : 0,
        total: device?.vram_total ?? 0,
        ram: system.ram_total ? 100 * (1 - system.ram_free / system.ram_total) : undefined,
    };
}

async function sample() {
    try {
        const stats = await readStats();
        peak = Math.max(peak, stats.used);
        const parts = [`VRAM ${gb(stats.used)}/${gb(stats.total)} GB`, `Peak ${gb(peak)}`];
        if (stats.ram !== undefined) parts.push(`RAM ${Math.round(stats.ram)}%`);
        if (stats.cpu !== undefined) parts.push(`CPU ${Math.round(stats.cpu)}%`);
        setLabel(buttons.stats, parts.join(" · "));
    } catch {
        // ComfyUI is restarting or busy; the next sample tries again
    }
}

function schedule() {
    clearTimeout(poll);
    poll = setTimeout(async () => {
        if (!document.hidden) await sample();
        schedule();
    }, running ? RUNNING_MS : IDLE_MS);
}

// ComfyUI's own /free route, the one behind its "Free model and node cache" menu entry.
async function freeMemory(unloadOnly) {
    const body = unloadOnly ? { unload_models: true } : { unload_models: true, free_memory: true };
    await api.fetchApi("/free", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    // The route only raises a flag; sample twice so the bar shows the memory going down.
    setTimeout(sample, 350);
    setTimeout(sample, 1400);
}

function runStarted() {
    running = true;
    peak = 0;
    runStart = performance.now();
    clearInterval(clock);
    clock = setInterval(() => setLabel(buttons.timer, clockText((performance.now() - runStart) / 1000)), 250);
    schedule();
}

function runEnded() {
    running = false;
    if (runStart !== null) setLabel(buttons.timer, clockText((performance.now() - runStart) / 1000));
    runStart = null;
    clearInterval(clock);
}

app.registerExtension({
    name: "RunBarAMD",
    actionBarButtons: Object.values(buttons),
    settings: [
        {
            id: SHOW_SETTING,
            category: ["Run Bar Monitor", "Run Bar", "Show"],
            name: "Show the run timer, memory readout and memory buttons next to Run",
            type: "boolean",
            defaultValue: true,
            onChange: () => applyVisibility(),
        },
    ],
    setup() {
        api.addEventListener("execution_start", runStarted);
        for (const event of ["execution_success", "execution_error", "execution_interrupted"]) {
            api.addEventListener(event, runEnded);
        }
        document.addEventListener("visibilitychange", () => { if (!document.hidden) sample(); });
        sample();
        schedule();
        applyVisibility();
    },
});
