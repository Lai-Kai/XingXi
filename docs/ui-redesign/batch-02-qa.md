# Batch 2 — 工作区与导航 QA

日期：2026-10-15（Asia/Shanghai）。Gemini 设计 v1.1.0，分支 feat/ui-redesign，起始提交 111f59dfa07c7c52ad67d7eb435c35cc8db2b385。代码尚未提交／推送。

## 结论

Batch 2 的工作区与侧栏实施完成，25 项框架／导航检查全部通过；Batch 1 原来通过的 55 项浏览器用例全部保持通过。合并浏览器结果 **80 通过、12 既有业务失败、0 未执行**，没有新增失败或页面横向溢出。完整业务验收仍未通过，不将本批完成等同于整套 UI 或业务缺陷全部完成。

[查看新版截图与前后对照](../../reports/ui-redesign/2026-10-15/batch-2/index.html) · [机器汇总](../../reports/ui-redesign/2026-10-15/batch-2/summary.json) · [代码及保护文件摘要](../../reports/ui-redesign/2026-10-15/batch-2/manifest.json)

## 实际验证

| 检查 | 结果 | 证据（本批目录下） |
| --- | --- | --- |
| 单元 | 108 文件／787 项通过 | unit-scroll-final/results.json、unit-scroll-final.log |
| ESLint | 0 error，4 条原有 graph-overview warning | lint-scroll-final.log、lint-scroll-final.exit.txt |
| TypeScript | 通过 | typecheck-scroll-final.log、typecheck-scroll-final.exit.txt |
| 默认 Next/Turbopack 构建 | 通过 | build-scroll-final.log、build-scroll-final.exit.txt |
| 工作区框架／导航 | 25 项通过：12 个新框架场景、7 个侧栏场景、6 个定时任务场景 | compatibility-e2e 与 scroll-validation-e2e |
| Batch 1 公共组件 | 13 项通过，8 张预览 | compatibility-e2e/ |
| 全部本轮浏览器用例，按名称合并 | 80 通过／12 既有失败／0 未执行 | summary.json；完整回归与后续补测 |
| 页面截图 | 四视口与原基线同条件 49 张，无新增横向溢出 | screenshots/ |
| 新框架截图 | 桌面展开／收起明暗、平板、390／360 手机页头与抽屉，共 13 张 | shell-screenshots/ |
| 原文件保护 | 设计文档／原型、包清单／lock、全局 app layout SHA256 均与 Batch 0 一致 | manifest.json |

证据根目录：`reports/ui-redesign/2026-10-15/batch-2/`。每轮保留日志、退出码、JSON 和 Playwright HTML 报告；失败保留 trace、图片与视频。

## 行为覆盖

- 桌面 260px／64px、反复拖拽折叠与拉开、224–480px 边界、Esc 撤销、窗口失焦及 body cursor／user-select 清理。
- Ctrl+B、Ctrl+K、跳转主工作区、折叠后的 tooltip；展开／收起 Cookie 刷新保持。
- 1024×768 默认图标栏，切换 1440／1024 视口自动适应；用户显式选择及 Cookie 优先，默认变化不产生 Cookie。
- 按 capability 显示导航：普通读者／研究者客户端刷新；admin 全部 13 入口。嵌套路由匹配与相似前缀隔离由单元覆盖，实际当前页 aria-current 由浏览器覆盖。
- 390×844、360×800 的明暗抽屉、48px 公共页头、44px 触控入口、独立滚动、底部账户与近期会话；桌面收起 Cookie 不隐藏手机导航内容。
- 抽屉 Tab／Shift+Tab、Esc 关闭返回原按钮、跳转后关闭；嵌套账户弹窗关闭后返回抽屉按钮。
- 360×640 短视口中，通过真实滚轮滚到定时任务表单底部，页头保持在顶部；不依赖 Playwright 自动滚入视口。
- 定时任务入口、会话过滤、创建、暂停、触发执行记录和过滤后的可见选择，使用现有 Mock API。
- 地图时间轴、位置详情、图层、路线导出、模型按需加载与失败重试等沿用旧用例；原定位检查已补测通过。

## 首轮问题与修正记录

1. 改前补跑 3 个桌面侧栏检查：1 通过、2 在动画中间读取尺寸失败，报告 before-sidebar 保留。新版轮询稳定尺寸，并考虑右侧 1px 边框；不删除拖拽／撤销／清理断言。
2. 侧栏旧测试仍要求通用 Agent 广场与旧欢迎语，已按单一星羲规则及实际文案修正；定时任务入口以稳定 href 定位。
3. 首轮本批框架共 24 项，17 通过／7 失败。发现受控 Radix Sheet／Dialog 没有 Trigger 时无法返回原焦点，已在业务组合层补齐，生成组件未改。另两项为上面的边框与旧欢迎语断言。完整重建后 24 项全部通过，首轮报告保留在 shell-e2e。
4. 完整回归单轮 91 项为 78 通过／13 失败，其中定位用例的授权 origin 仍取 localhost:3000，与隔离的 127.0.0.1:3106 不同。设置 PLAYWRIGHT_BASE_URL 后该项单独通过，未改定位代码或原断言。按文件＋测试名采用补测结果，合并为 79／12／0。
5. 最后明确 WorkspaceBody 的 overflow-y-auto 并补短视口滚轮场景，重新构建、单元／类型／lint 和 46 项受影响的兼容检查。兼容轮 45 通过／1 个滚轮夹具失败：初始样本 800px 未超高，改为 640px 后鼠标坐标仍在视口外；修正坐标后滚轮专项通过。合并最终兼容 46 项全部通过；完整回归按名称去重为 92 项，80 通过／12 既有失败。scroll-before、scroll-baseline、compatibility-e2e 和 scroll-validation-e2e 保留全过程，不把夹具问题称作已证实的产品缺陷。
6. 页面截图在字体就绪后再等待两个绘制帧，避免导航内容尚未完整绘制的中间截图；49 张最终页面截图已全部重采集。预览下拉切换、四张图片加载和本地链接均经浏览器检查。

## 仍存在的旧失败与范围

剩余 12 项与 Batch 1 对应失败相同：图谱概览／审核 5、GLB 移动／桌面 viewer 数量 1、项目关联证据 1、文献审核／发布入口 3、首页／规范聊天入口 2。定时任务的 1 个入口失败已随导航实施修复，原先 serial 跳过的后续 5 项也全部通过。

本轮为本机 Chrome、已有软件测试 auth-disabled 模式和 Mock API；没有真实 Gateway、服务端权限或生产业务数据验收。评测页不可用 Mock 的 loading 状态仍与前批相同。实体手机／虚拟键盘、触控手势与模型质量未验收。

首页、聊天内容／Evidence Inspector、文献／地图／图谱主体，以及其他页面完整视觉继续由 Batch 3／4 实施。聊天保留其原工具栏；公共业务页头和兼容页头接入检索入口。现存页面的浅色硬编码、页面内容的最大宽度及详情面板并非本批全部迁移项。最终 Gemini 视觉复核与完整验收在 Batch 5。
