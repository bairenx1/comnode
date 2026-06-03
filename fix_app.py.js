const fs = require("fs");
const path = require("path");
const projectDir = "C:\\Work\\comfy\\ComfyUI";
const iconv = require(path.join(projectDir, "..", "comfyui-nodestudio", "node_modules", "iconv-lite"));

const filepath = path.join(projectDir, "custom_webui", "backend", "app.py");
const buf = fs.readFileSync(filepath);
const corrupted = buf.toString("utf-8");
const gbkBytes = iconv.encode(corrupted, "gbk");
const original = gbkBytes.toString("utf-8");

// Check if the fix looks correct
if (original.includes("请先启动") && original.includes("ComfyUI")) {
    console.log("Fix confirmed! Writing file...");
    fs.writeFileSync(filepath, original, "utf-8");
    console.log("SUCCESS");
} else {
    console.log("Fix may not be correct. Sample around hint:");
    const idx = original.indexOf("comfyui_unavailable");
    if (idx >= 0) console.log(original.substring(idx, idx + 120));
}
