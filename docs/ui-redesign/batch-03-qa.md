# Batch 3 — 核心页面 QA

日期：2026-10-15（Asia/Shanghai）。设计 Gemini v1.1.0，分支 `feat/ui-redesign`，起始提交 `111f59dfa07c7c52ad67d7eb435c35cc8db2b385`。本轮未提交／推送。

## 结论

用户指定的首页、聊天／Evidence Inspector、古舆地图三页已实施。**核心与兼容专项 74 项全部通过**：修正后的 72 项软件浏览器检查，加 1 项真实 OSM 补测和 1 项粗指针触控专项。110 个单元文件／794 项通过，类型与构建通过，lint 0 error／4 条原有 graph-overview warning。

扩展回归按「文件＋用例名」合并，最终 **133 通过、16 未通过、0 跳过，共 149 项**。其中 Batch 2 同组 92 项全部重跑：82 通过／10 项相同旧失败，原 80 项通过项没有新增失败；首页即时 URL 断言和 GLB 嵌套弹窗退出时序两项经测试修正后通过。新增检查范围中的 6 项失败另列，不能据此宣称整套业务验收通过。

[查看三页与真实底图截图](../../reports/ui-redesign/2026-10-15/batch-3/index.html) · [机器汇总](../../reports/ui-redesign/2026-10-15/batch-3/summary.json) · [构建与文件摘要](../../reports/ui-redesign/2026-10-15/batch-3/manifest.json)

## 实际结果

证据根目录：`reports/ui-redesign/2026-10-15/batch-3/`。

| 检查 | 最终结果 | 证据 |
| --- | --- | --- |
| 单元 | 110 文件／794 项通过 | `unit-refinement/results.json`、`unit-refinement.log` |
| TypeScript | 通过，退出码 0 | `typecheck-refinement.log`、`.exit.txt` |
| ESLint | 0 error／4 条原 warning；新增真实底图测试单独 lint 通过 | `lint-refinement.log`、`lint-live.log` |
| Next/Turbopack 构建 | 通过，退出码 0 | `build-touch.log`、`.exit.txt` |
| 三页四视口明暗矩阵、IME／历史日期、Evidence 重试／竞态、滑块／缓存、真实 GLB | 12 项通过 | `refinement-e2e/` 中 `ui-redesign-core.spec.ts` |
| 聊天／sidecar | 20＋7 项通过；线程分支另 1 项通过 | `refinement-e2e/`、`final-e2e/` |
| 原地图／模型行为 | 8＋5 项通过 | `refinement-e2e/` |
| 基础组件与页面基线 | 13＋7 项通过 | `refinement-e2e/` |
| 真实 OSM | 1 项通过：1440 桌面与 390 手机，真实瓦片＋本地 GLB | `live-map-final-e2e/` |
| 粗指针触控 | 1 项通过：引用、地图与 Portal 内模型控制的 44px 热区、触控打开、单 viewer | `touch-final-e2e/` |
| 框架／导航／任务 | 12＋7＋6 项通过 | `final-e2e/` |
| 前批额外兼容补测 | 评测、页面溢出、文献注册共 3 项通过 | `validation-e2e/` |
| 全部用例去重 | 133 通过／16 未通过／0 跳过 | `summary.json`，不是某一单轮报告的计数 |
| 截图 | 核心 29、同条件页面 49、框架 13、组件 8 | `core-screenshots/`、`screenshots/`、`shell-screenshots/`、`refinement-e2e/` |
| 原文件保护 | 设计／原型、app layout、package／lock SHA256 与 Batch 0 一致 | `manifest.json` |

## 覆盖的业务与交互

- 首页水墨资源成功加载；1440／1024／390／360 明暗主题无页面横向溢出。课题输入保留中文 IME、Shift+Enter，tab 支持方向键／Home／End；日期筛选基于已有历史接口。选题深链接保留 `topic_query`、`document_id` 和 `evidence_id`。
- 引文先变为安全的既有站内路径，再交给原 Markdown URL 过滤器。单元覆盖真实 Markdown 渲染、编码、非本站链接、代码／图片节点与危险协议过滤。
- 桌面 380px／平板 420px／手机 65dvh 考据面板；来源卷页和摘录可读。引用不跳离对话，关闭返回焦点，手机下拉手柄可关闭。失败后可重试，迟到的上一出处响应不能覆盖新选择。
- 对话保留润色／撤销／取消、技能建议与键盘、发送流、goal、附件限制／元数据／提交期间可见性、模板占位阻断、follow-up 开关。Sidecar 的引用创建、历史恢复、删除与失败状态通过。原 human-input／compact 等单元随全量运行通过；未将其记为真实服务验收。
- 地图保持原 OSM 层和署名，按需打开模型，7 个模型绑定保持原登记。新滑块支持键盘与清空，前后事件、原播放、定位、路线编辑／导出、图层和未知／推测范围行为通过；交互不重新请求目录。
- 地图根据真实面板尺寸留出相机安全区域，避免点位被时间轴或右面板遮挡。正常点位点击与手机立即打开详情通过。
- 真实 GLB 检查包含加载／失败重试、自动旋转／复位、同一个元素放大、手机／桌面切换、晚到资源不能覆盖新选择、固定尺寸标点。来源／许可和「生成示意」提示保留。

## 首轮问题与修正

1. 原 Markdown 标准 URL 过滤会清空 `evidence://`。新增业务层 rehype 适配，只转换出处锚点，不放宽危险协议；4 项安全单元和真实浏览器引用联动通过。
2. 手机考据抽屉的宽泛 close-button 样式误隐藏手柄，原文也排在较长元数据之后。缩小选择器范围并前移原文；补测手柄下滑与关闭焦点。桌面打开 Inspector 时关闭引用 hover card，避免遮盖正文。
3. 浮动时间轴遮住原相机中心。测量 HUD／时间轴／详情尺寸并传入 padding；旧居中断言按实际可见地图区域调整，继续检查聚焦与缩放，不移除断言。断网提示移到工具栏下，深色外围面板与引文改用语义 Token。
4. 模型旧测试在嵌套 Dialog 退出动画尚未移除时按 Escape，事件被旧层接收。测试先等待该层卸载，再验证父 Sheet 关闭和 viewer 释放。另将首次 marker 滚入视口放在相机稳定后，消除节点重建竞态；行为断言保留。
5. 聊天旧用例仍用 DeerFlow 输入占位语，且 Mock 的模型列表为空。按现有星羲文案更新选择器，为发送测试配置测试模型；没有改变无模型时禁止发送的产品行为。首页测试适配新卡片／偏好区作用域并等待真实导航。
6. 新对话题签与卡片样式最初也作用于 sidecar，历史恢复检查出现多次滚动。将新卡片范围限定为主对话，sidecar 保留原消息布局，7 项检查通过。
7. 首次基础组件补测遗漏显式 SSR fixture 环境变量而跳过 12 项；生成 fixture 后 13 项全部执行通过，首轮结果保留。首次真实 OSM 测试的目录夹具只有署名文字，测试却要求署名链接；补齐真实 attribution 格式后通过。原色、透明度与成功瓦片响应断言保留。
8. 初轮文件名过滤误纳入 generic agent-chat，用例与单一星羲产品不符。该探索轮保留在 `business-e2e/`，最终合并只使用明确选定文件的回归轮，不恢复 Agent 广场，也不将探索轮失败藏进成功计数。
9. 最终触控检查为实际研究页补齐粗指针下的引用、地图缩放、模型放大／关闭热区；原 28px 标点圆不变，点击区域保持 44px。首次测试在 Dialog 缩放入场期间测得约 42.7px，改为轮询静止尺寸后，44px 断言和实际 tap 全部通过；未放宽尺寸阈值。

静态交付页另外检查了 24 组页面／视口／主题切换、全部核心图片、前后对照图片与 9 个本地链接，0 页面脚本异常；结果见 `preview-validation.json`。

## 剩余问题与限制

Batch 2 已有且本轮仍失败的 10 项：图谱 overview／审核 5、研究项目关联证据 1、文献审核／发布 3、canonical 星羲入口的 `Cannot read properties of null (reading 'promise')` 1。

本轮额外扩大检查的 6 项未通过，前批没有这些用例的对照，不能标成「已确认旧失败」或「已确认本批产品回归」：

- `knowledge-graph.spec.ts` 2 项，涉及旧关系深度入口／控件；图谱主体未在本批重构。
- `thread-history.spec.ts` 4 项：1 项仍查找已不存在的旧侧栏新对话 href，3 项仍查找 `how can i assist you`。测试在旧入口／文案阶段失败，对应历史重置／删除场景未获得本轮通过证据；9 项其余历史行为与分支通过，后续应适配夹具并重验。

软件服务使用本机 Chrome 和隔离 `127.0.0.1:3106`、既有 SSR auth-disabled 模式与 Mock API。仅明确的真实 OSM 补测联网，GLB 为真实本地资产。没有启动真实 Gateway、生产模型、Replay Gateway 或发布写入。接口未返回的独立 OCR 影印／Release 元数据没有新增；实体手机、虚拟键盘、真实触摸、服务端授权、全量模型史实质量与 Gemini 最终视觉复核尚未验收。

## 复现

在 `frontend` 使用已安装依赖的 Node bin。项目声明 pnpm 10.26.2，而本机 bundled pnpm 为 11.25.0，因此本轮直接运行本地工具，没有安装／改动包或锁文件。

```powershell
node node_modules/@rstest/core/bin/rstest.js run
node node_modules/eslint/bin/eslint.js . --ext .ts,.tsx
node node_modules/typescript/bin/tsc --noEmit
$env:SKIP_ENV_VALIDATION='1'
$env:DEER_FLOW_AUTH_DISABLED='1'
node node_modules/next/dist/bin/next build
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3106'
node node_modules/@playwright/test/cli.js test --config playwright.ui-redesign.config.ts '[/\\](ui-redesign-core|ui-redesign-foundations|ui-redesign-baseline|map-business|map-model-preview|chat|sidecar-chat)\.spec\.ts$'
$env:UI_LIVE_OSM='1'
node node_modules/@playwright/test/cli.js test --config playwright.ui-redesign.config.ts ui-redesign-core.spec.ts --grep 'real OSM'
```

每轮另设置独立 `TEST_REPORT_DIR`；组件测试需设置 `FOUNDATION_PREVIEW_PATH` 并先由单元生成 fixture，截图使用 `UI_CORE_DIR`／`UI_BASELINE_DIR`／`UI_SHELL_DIR`。日志与退出码保留在本批证据目录。最后运行 `collect-evidence.mjs` 生成按名称合并的汇总和静态预览，不能简单累加重复轮次。
