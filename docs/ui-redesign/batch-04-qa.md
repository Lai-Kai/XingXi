# Batch 4 — 管理与专业页面 QA

日期：2026-10-15，Asia/Shanghai。Gemini v1.1.0；分支 `feat/ui-redesign`，起点 `111f59dfa07c7c52ad67d7eb435c35cc8db2b385`。未提交、推送或发布。

## 结论

用户指定的文献库、知识图谱、质量中心、Agent 评测、运营中心与定时任务六页已实施。最终单元 **110 文件／794 项通过**；类型、构建通过，lint **0 error／4 条原警告**。三份最终浏览器报告按「文件＋用例名」去重，**97 通过／0 失败／0 跳过**。改前同组 38 项为 23 通过／15 未通过，最终 38 项全部通过；15 项恢复，原通过项没有退化。

这是本批明确范围的结果，不能描述为整套业务已全部验收。Batch 3 留存的 6 项范围外失败本批未重跑，详情见下文。

[查看六页及专业流程](../../reports/ui-redesign/2026-10-15/batch-4/index.html) · [逐项汇总](../../reports/ui-redesign/2026-10-15/batch-4/summary.json) · [文件与构建摘要](../../reports/ui-redesign/2026-10-15/batch-4/manifest.json)

## 实际检查

证据根目录：`reports/ui-redesign/2026-10-15/batch-4/`。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Rstest | 110 文件／794 项通过 | `unit-final.log`、`unit-final/results.json` |
| TypeScript | 退出码 0 | `type-final.log`、`.exit.txt` |
| ESLint | 0 error／4 条原 graph-overview 警告 | `lint-final.log`、`.exit.txt` |
| Next 生产构建 | 退出码 0 | `build-final.log`、`.exit.txt` |
| 六页四视口明暗矩阵 | 8 项通过，48 张图，无横向溢出或 pageerror | `workflow-final-e2e/`、`admin-screenshots/` |
| 复核／发布／质量／权限／管理刷新专项 | 6 项通过 | `workflow-final-e2e/` |
| 原业务回归 | 38 项通过 | `final-e2e/`、`compatibility-final-e2e/` |
| 前批核心、导航、公共组件、路由基线 | 13＋12＋13＋7 项通过 | `final-e2e/` |
| 最终去重 | 97 通过／0 失败／0 跳过 | `summary.json`，不累加同一用例的重复执行 |
| 截图 | 本批 53、前批核心 27、框架 13、全路由 49；组件另 8 | 各截图目录及 `final-e2e/foundations-*.png` |
| 独立预览入口 | 5 组／142 张图解码、5 个链接、手机宽度与切换通过 | `preview-validation.json`、`preview.png` |
| 文件保护 | app layout、package／lock、设计系统与原型 SHA256 与 Batch 0 相同 | `manifest.json` |

原业务 38 项细分：Agent 自动流程 1、评测仪表板 8、图谱总览 7、审核 7、主体关系网 2、人工评测 1、运营 1、定时任务 6、文献复核 3、文献权限 1、首次登记 1。

## 业务与失败恢复

- 文献审核实际加载原始／清洗文本、未知 OCR 置信度显示「未采集」，不显示 0%。测试影印通过原 content URL 成功加载，并明确注明「软件测试影印 · 非真实古籍」。争议无意见时不发请求；填写后验证 `items` 中精确 target ID、decision 和 comment。按页及片段通过后再测试发布，验证 exact ChunkSet 与 `expected_state_version`。
- 复核 409 和发布指针 409 均显示错误，保留已填意见、旧状态和版本校验值，可以重试。没有将客户端按钮成功当作真实发布事务验收；实际事务仍由 Gateway 决定。
- 质量手机处理保存失败时意见保留、重试后保存、Escape 关闭后回到原按钮。quality:read 只出现查看，不能填写或保存处理结果。桌面与手机复用同一份详情内容。
- 图谱 ordinary／admin 边界、无 Evidence 禁通过、失败保留审核备注、关系／事件反复改判及刷新、已驳回过滤全部保留原断言。专业工作台显式 `manage=1` 可刷新恢复；待考转争议时意见必填。
- Agent 评测保留真实批次统计、未完成／空结果不报全通过、缺失耗时、筛选与轨迹、旧请求竞态、读取角色、无权限与失败恢复；原自动流程的失败／复核／导出／取消后重跑检查通过。
- 运营缺失比率显示暂无数据，三维指标显示未接入，不造图表趋势。热门实体横条对应真实返回计数。任务创建／暂停／恢复／删除／运行记录和手机长表单滚动回归通过。
- 四种宽度为 1440／1024／390／360；每种明暗主题。管理页面粗指针控件样式遵循 44px；本批未将实体触摸设备作为已完成验收。

## 首轮问题及修正

1. 旧文献夹具遗漏现有分页目录接口，新专项又误用不存在的 `/chunk-sets`，已分别补齐真实 `/library/page` 和 `/files/{id}/chunks`。保留上传、Raw／Clean 与窄屏断言，没有改产品 API。
2. 图谱旧专业用例依赖直接进入管理视图，改用已支持的 `manage=1`；普通读者用例等待实际 `/auth/me` 返回，避免在 hydration 前派发一次事件导致角色未刷新。审核请求和无权限断言仍在；不改产品 AuthProvider。
3. 评测错误用例等待时长覆盖原 React Query 重试；人工评测相同回答出现在结果与历史时，选择器限定「最近一次结果」。运营夹具补齐原 tasks 请求。最后中心断言改为实际保留的最近主体。
4. 手机反馈保存刷新原来会卸载整列记录，导致关闭焦点丢失；刷新已有内容时保留列表 DOM。失败仅在详情提示，不把未保存意见换成整页错误。
5. 截图发现定时表单挤占页头行、手机指标过长、默认图谱显示另一请求范围的零计数、缩略图深色白底。已修正网格行、手机两列统计、管理统计显示范围及缩略图主题。

改前、初版及最终日志分别保留于 `before-e2e/`、`business-e2e/`、`admin-e2e/` 和最终目录；不将中间失败覆盖为未发生。

## 环境与未验收部分

- 本机 Node v24.19.0、项目已有依赖、Chrome；直接运行已安装 package bin。生产构建用于 `127.0.0.1:3106` 隔离前端，SSR auth-disabled 与 Mock 领域 API。未连接真实 Gateway；部分日志中的 8001 ECONNREFUSED 来自不可用本地服务，不作为服务端成功证据。
- 原件预览展示已上传原文件，PDF 页定位由浏览器 PDF 支持决定；没有独立 OCR 页图／区域坐标，不能声称已完成区域框联动或精确图像切片。
- 发布准备／激活／回滚、真实数据库、服务器授权、任务实际后台执行与真实模型质量需联调。fixture 的成功不代替服务端原子性与权限验收。
- Batch 3 的 `research-project-workspace.spec.ts` 1 项、`thread-history.spec.ts` 4 项及 `xingxi-home.spec.ts` canonical null promise 1 项本批未重跑；保留原问题状态，不计入本批 97 项。图谱原失败中 7 项与文献 3 项已通过当前适配回归，但这不能关闭整个历史问题列表。
- 项目、展签、异名、登录及其他次级页面完整重构、实体手机、全套无障碍／动效和 Gemini 最终视觉复核仍为后续范围。

## 复现

在 frontend 使用已有依赖：`node node_modules/@rstest/core/bin/rstest.js run`、`node node_modules/typescript/bin/tsc --noEmit`、`node node_modules/eslint/bin/eslint.js . --ext .ts,.tsx`。构建设置 `SKIP_ENV_VALIDATION=1`、`DEER_FLOW_AUTH_DISABLED=1` 后执行 `node node_modules/next/dist/bin/next build`。

浏览器使用 `playwright.ui-redesign.config.ts`，必须设置 `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3106` 和独立 `TEST_REPORT_DIR`。矩阵截图设置 `UI_ADMIN_DIR`；基础组件设置 `FOUNDATION_PREVIEW_PATH` 到已有的 `batch-3/foundations.html`。完整用例文件／名称与最终来源见 `summary.json`；预览收集与校验脚本保存在证据根目录。
