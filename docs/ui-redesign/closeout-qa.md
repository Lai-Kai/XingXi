# UI 整体收尾：辅助页面核对与联调准备

日期：2026-10-15。分支 `feat/ui-redesign`；设计 Gemini v1.1.0。未提交、推送或发布。

## 完成情况

本轮补充核对古文展签、异名辨析、研究项目及其工作区、登录页。展签／异名／项目列表与详情四个文件的固定浅色样式迁移为现有语义 Token，保留原 API、状态、输入和权限；登录页保留现有实现，新增独立关闭 SSR 认证绕过的检查。

最终 **112 项浏览器检查全部通过，0 失败／0 跳过**。其中 Batch 4 的 97 项全部重跑并保持通过，新增辅助页 14 项、项目工作区 1 项。**110 文件／794 单元通过，类型／构建通过，lint 0 error／4 条原警告**。根 README 最前新增本次收尾暨 Batch 3／4 汇总记录，原逐批记录保留。

[辅助页与结果预览](../../reports/ui-redesign/2026-10-15/closeout/index.html) · [逐项检查汇总](../../reports/ui-redesign/2026-10-15/closeout/summary.json) · [真实环境演练步骤](gateway-integration-runbook.md)

## 四个入口

| 入口 | 本次确认 | 尚需真实环境验证 |
| --- | --- | --- |
| `/workspace/glossary` | 输入／错误恢复、原文保留、来源、待考提示、复制内容与打印入口；主题与四屏宽 | 实际释读结果、史料质量与打印实体效果 |
| `/workspace/name-authority` | 缺少依据时禁提交、Evidence ID 去重、错误不丢候选、歧义保留全部异名、不强行选名 | 数据库真实依据、权威度计算与人工审核质量 |
| `/workspace/projects` 及详情 | 创建／IME、读取失败重试、普通读者权限、文献关联、问题记录、项目范围检索、出处及助手深链接 | 服务端项目授权、真实资料范围与重启持久化 |
| `/login` | 正常表单、失败保留输入、SSO 入口、安全返回路径、初始化入口与禁止普通注册；主题与四屏宽 | 真实 Cookie／CSRF、登录成功、SSO 回调及数据库会话 |

`playwright.ui-closeout.config.ts` 同时使用已有构建：3106 的工作区允许 SSR 测试绕过，3107 的登录页关闭绕过。登录页通过真实 AuthLayout 的未登录分支呈现，浏览器接口仍由测试夹具模拟；没有声称已完成真实鉴权联调。

## 验证证据

证据根目录 `reports/ui-redesign/2026-10-15/closeout/`。

| 检查 | 结果 | 文件 |
| --- | --- | --- |
| 单元 | 110 文件／794 项通过 | `unit.log`、`unit/results.json`、`unit.exit.txt` |
| 类型 | 退出码 0 | `type-final.log`、`.exit.txt` |
| 代码规范 | 0 error／4 条原 graph-overview warning | `lint-final.log`、`.exit.txt` |
| 生产构建 | 退出码 0 | `build-final.log`、`.exit.txt` |
| 完整本批浏览器回归 | 112 通过／0 失败／0 跳过，前批 97 项无退化 | `final-e2e/results.json`、`final-e2e.log`、`summary.json` |
| 辅助矩阵 | 5 个画面 × 4 屏宽 × 2 主题，共 40 张 | `screenshots/` |
| 业务结果 | 展签／异名结果、项目已关联资料的桌面／手机，共 4 张 | `screenshots/` |
| 文件保护 | app layout、package／lock、设计规格与原型摘要和前批相同 | `manifest.json` |
| 联调前置只读核对 | 未启动服务、未验证数据库连接 | `environment-readiness.json` |
| 独立预览 | 44 张图解码、8 个链接、手机宽度与切换通过 | `preview-validation.json`、`preview.png` |

四屏宽为 1440／1024／390／360。测试验证无文档横向溢出、页面无运行异常。已有生成组件、core API／权限、backend、数据库配置和设计定稿未修改。

本轮重跑包括前批首页／聊天考据／地图核心 13 项、导航 12 项、公共组件 13 项、路由基线 7 项、专业页面 14 项和原业务 38 项。真实 OSM 专项保留 Batch 3 的历史证据，本轮没有重复访问真实瓦片；软件浏览器成功不代表模型史实质量。

## 失败排查与保留记录

1. 改前项目工作区用例失败在旧文案「查看关联证据」；实际入口为「查看关联资料出处」。保留项目文献范围、记录、检索和深链接断言，适配文案后通过。此前 Batch 3／4 留存的这一项现已恢复。
2. 新辅助夹具遗漏项目详情同时加载的分页来源接口，补齐后矩阵通过。原文字段的可访问名还包含字数，展签结果和 textarea 又有同一原文；选择器按字段前缀与结果 article 定位，不改产品输入含义。
3. Next 路由 announcer 也是 alert；错误断言限定业务 main，仍核对具体错误内容。重试按钮使用真实「重新加载」文案。复制与打印用浏览器内测试替身记录调用，不写系统剪贴板、不打开系统打印窗口。
4. 中间报告保留：`before-e2e/`（项目旧失败）、`secondary-e2e/`（11 失败／4 通过）、`secondary-final-e2e/`（1 失败／14 通过）；最终以一次完整 `final-e2e/` 的 112 项结果为准，不累加重复执行。

## 后续边界

- 当前本机快照：SQLite 配置、Gateway 不可达、Docker 命令存在但默认 engine pipe 未就绪；uv／make 不在当前 PowerShell PATH，数据库连接未验证。已准备真实联调前置条件、启动顺序、最小业务链与证据清单，尚未执行。
- 原 6 项范围外历史失败中的项目用例本轮通过；**历史聊天 4 项与 canonical 入口 null promise 1 项仍未重跑，共 5 项**。它们不计入当前 112 项绿色报告，问题状态继续保留。
- 全部次级内容路由、设置的完整重构、实体触摸设备、200% 缩放／全套无障碍、真实 Gateway／数据库与 Gemini 最终视觉复核尚未完成，不能把本次收尾写为 Batch 5 或全系统验收完成。
- 独立 OCR 页图／区域坐标接口仍未提供；原件预览不等于 OCR 区域框定位。

## 复现

在 frontend 使用已有工具链运行类型、lint、Rstest 和构建。浏览器使用 `playwright.ui-closeout.config.ts`，设置 `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3106`、独立 `TEST_REPORT_DIR`；辅助截图设置 `UI_SECONDARY_DIR`，基础组件设置 `FOUNDATION_PREVIEW_PATH` 为已保存的 `batch-3/foundations.html`。完整 18 个测试文件及逐项名称见 summary；登录检查需要配置中的 3107 服务同时可用。
