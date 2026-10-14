const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const root = path.resolve(__dirname, "../../..");
const frontend = path.join(root, "frontend");
const frontendRequire = createRequire(path.join(frontend, "package.json"));
const esbuild = frontendRequire("./node_modules/.pnpm/esbuild@0.27.7/node_modules/esbuild");
const postcss = frontendRequire("postcss");
const tailwind = frontendRequire("@tailwindcss/postcss");
const snapshot = JSON.parse(fs.readFileSync(path.join(__dirname, "snapshot.json"), "utf8"));
const options = { bundle: true, write: false, jsx: "automatic", alias: { "@": path.join(frontend, "src") }, nodePaths: [path.join(frontend, "node_modules")] };

async function main() {
  const server = esbuild.buildSync({
    ...options, platform: "node", format: "cjs", stdin: {
      contents: `import { createElement } from "react"; import { renderToString } from "react-dom/server"; import { ManualEvaluations } from "@/components/workspace/manual-evaluations"; export const render = (snapshot) => renderToString(createElement(ManualEvaluations, { ...snapshot, observations: {}, saving: false, onObservation: () => {}, onRun: async () => {}, onCreateCase: async () => {} }));`,
      resolveDir: frontend,
    },
  }).outputFiles[0].text;
  const serverPath = path.join(__dirname, "render.cjs");
  fs.writeFileSync(serverPath, server);
  const markup = require(serverPath).render(snapshot);
  const browser = esbuild.buildSync({ ...options, entryPoints: [path.join(__dirname, "preview.tsx")], platform: "browser", minify: true }).outputFiles[0].text;
  const css = await postcss([tailwind({ base: frontend })]).process(
    `@import "tailwindcss" source(none); @source "${path.join(frontend, "src/components/workspace/manual-evaluations.tsx")}";`,
    { from: path.join(frontend, "simple-demo.css") },
  );
  const document = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>星羲 · 简单测试演示</title>
<style>${css.css}</style><style>body{margin:0;background:#f7fafb;color:#202b2e;font-family:system-ui,"Noto Sans CJK SC","Microsoft YaHei",sans-serif}main{max-width:980px;margin:0 auto;padding:36px 24px}header{display:flex;align-items:center;gap:12px;margin-bottom:28px}.brand{display:flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:10px;background:#205f68;color:white;font-weight:700}.note{margin:0 0 24px;padding:12px 16px;border:1px solid #d7e1e2;border-radius:8px;background:white;color:#53676c;font-size:13px;line-height:1.8}.subtitle{color:#697a7f;font-size:12px}summary{list-style-position:inside}button,summary,select{cursor:pointer}button:disabled{cursor:default}button:focus-visible,summary:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:2px solid #276f79;outline-offset:3px}@media(max-width:600px){main{padding:24px 16px}}</style></head>
<body><main><header><div class="brand">羲</div><div><strong>星羲 · 运营中心</strong><div class="subtitle">回归评测 / 简单测试</div></div></header>
<p class="note">已使用你提供的完整回答生成演示记录，可直接查看效果。展开“录入下一次回答”可以体验通过或失败的显示。预览中的新操作只保存在当前页面。</p>
<div id="demo">${markup}</div></main>
<script>window.demoSnapshot=${JSON.stringify(snapshot).replace(/</g, "\\u003c")};</script>
<script>${browser.replace(/<\/script/gi, "<\\/script")}</script></body></html>`;
  const output = path.join(root, "reports/testing/simple-demo/index.html");
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, document);
  fs.copyFileSync(path.join(__dirname, "snapshot.json"), path.join(path.dirname(output), "results.json"));
  console.log(output);
  console.log(`Self-contained HTML: ${Buffer.byteLength(document)} bytes; latest result: ${snapshot.runs[0].passed}/${snapshot.runs[0].total}`);
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
