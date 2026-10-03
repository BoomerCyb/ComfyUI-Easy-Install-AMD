import { app } from '../../../scripts/app.js';

app.registerExtension({
    name: 'Nunchaku.AMD.LayerReport',
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== 'NunchakuAMDQwenLayerTest') return;
        const previous = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            previous?.apply(this, arguments);
            if (!this.nunchakuReport) {
                const textarea = document.createElement('textarea');
                textarea.readOnly = true;
                textarea.style.cssText = 'width:100%;height:100%;resize:none;font:12px monospace;';
                const widget = this.addDOMWidget('nunchaku_report', 'text', textarea, {
                    serialize: false,
                    getValue: () => textarea.value,
                    setValue: value => { textarea.value = value; }
                });
                widget.computeSize = () => [480, 260];
                this.nunchakuReport = textarea;
            }
            this.nunchakuReport.value = (message.text ?? []).join('\n');
            this.setSize([Math.max(500, this.size[0]), Math.max(480, this.size[1])]);
            this.setDirtyCanvas(true, true);
        };
    }
});
