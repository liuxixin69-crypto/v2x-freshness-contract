"use strict";
/*
 * 把 数据/预警可行域_heatmap.json 内嵌进 v0.2 模板，产出离线单文件原型。
 * 之所以内嵌：file:// 下 fetch 本地 JSON 会被浏览器拦，现场又要求断网可用。
 *
 * 运行： node 代码/build_prototype.js
 * 输入： 代码/v0.2.template.html + 数据/预警可行域_heatmap.json
 * 输出： 产品原型/v2x_预警死线_v0.2.html
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const tpl = fs.readFileSync(path.join(__dirname, "v0.2.template.html"), "utf8");
const data = fs.readFileSync(path.join(ROOT, "数据", "预警可行域_heatmap.json"), "utf8");

if (!tpl.includes("__HEATMAP_JSON__")) throw new Error("模板缺少 __HEATMAP_JSON__ 占位符");
// 防止 JSON 里意外出现 </script> 造成提前闭合
if (/<\/script/i.test(data)) throw new Error("热力图数据包含非法的 </script>");
const html = tpl.replace("__HEATMAP_JSON__", data);

// 编译期语法检查（只编译，不执行 DOM 代码）
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
  .map(m => m[1]).filter(s => s.trim() && !s.trim().startsWith("{"));
scripts.forEach((s, i) => {
  try { new Function(s); }
  catch (e) { throw new Error("内联脚本 #" + (i + 1) + " 语法错误: " + e.message); }
});

const out = path.join(ROOT, "产品原型", "v2x_预警死线_v0.2.html");
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, html, "utf8");
console.log("生成:", out);
console.log("大小:", (Buffer.byteLength(html, "utf8") / 1024).toFixed(1), "KB");
console.log("内联脚本编译检查:", scripts.length, "段通过");
console.log("内嵌热力图:", JSON.parse(data).meta.losses.length, "列 x",
  JSON.parse(data).meta.taus.length, "行 x 3 场景");
