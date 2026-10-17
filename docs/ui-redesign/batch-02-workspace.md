# Batch 2 — 全局工作区布局与侧栏

设计：Gemini v1.1.0，第 2 节全局信息架构与第 7 节响应式规格。代码以 Batch 1 为起点，分支 feat/ui-redesign。

## 实施范围

- 导航分为核心研究、时空人文、文献与治理；保留既有 12 个路由入口，按设计补上已有的定时任务页面，共 13 项。星羲研究助手仍指向 `/workspace/agent`，最近研究仍指向 `/workspace/chats`；不新增通用 Agent 广场。
- 管理类入口沿用 source:manage、project:manage、quality:read、governance:read，未改权限契约。导航按完整路径段标记当前页，嵌套路由保持归属，不把 `/workspace/agents` 误判为 `/workspace/agent`。
- 桌面默认 260px，可收起为 64px；保留 224–480px 拖拽范围、160px 折叠阈值、Pointer Capture、Esc 撤销、窗口失焦和卸载清理。
- 没有保存偏好时，768–1199px 默认图标栏；Cookie 和用户操作优先。自动响应断点不写 Cookie，显式操作继续通过原 SidebarProvider 写 sidebar_state。
- 左上使用影青瓷徽标与星羲弦沚名称，底部提供设置、业务身份／组织与账户入口。徽标加载失败可回退。
- 手机保留 Radix Sheet 的遮罩、焦点锁定和 Esc 退出；桌面收起 Cookie 不隐藏手机导航文字或近期会话。点击导航关闭抽屉，设置作为嵌套弹窗保留抽屉与焦点。
- 公共业务页头 48px，切换和检索目标 44px；聊天保留现有标题与工具操作。兼容页头与地图仅调整框架入口，页面内容与证据布局留给 Batch 3／4。
- 外框使用动态视口高度，保留页面滚动容器，提供键盘跳转工作区内容的链接。
- 兼容页面 WorkspaceBody 明确负责纵向滚动，360×640 短视口的定时任务长表单通过真实滚轮可达底部，页头保持固定。截图在字体就绪后等待两个绘制帧，保证导航完整绘制。

## 文件所有权

- workspace-navigation.ts：分组／客户端可见性／激活匹配／页头标题。
- workspace-sidebar.tsx、workspace-header.tsx、workspace-nav-chat-list.tsx、workspace-nav-menu.tsx：品牌、导航、身份与组合布局。
- resizable-sidebar.tsx：响应断点默认值和原缩放生命周期。
- workspace-mobile-header.tsx、business-page.tsx、workspace-container.tsx：手机入口与公共页头。
- app/workspace/workspace-content.tsx：保留 Cookie、Provider、离线 Banner 和命令面板组合。
- styles/xingxi-workspace.css：业务级布局覆盖；生成的 ui/、ai-elements/ 保持原样。
- recent-chat-list.tsx：保留分页、删除、重命名／IME、导出和分享操作，新增手机跳转后关闭和 aria-current。

## 资产

`frontend/public/brand/xingxi-celadon-emblem.jpg` 原样复制自：

`C:/Users/蒲煜元/.gemini/antigravity/brain/cd77d99f-5c52-4d28-b5ae-6c9bb4202348/xingxi_brand_celadon_emblem_1792033808162.jpg`

Gemini 设计文档标注来源为 AI 艺术定制 (Gemini Image Studio, XingXi Project)。未编辑原图；通过 Next Image 请求适配尺寸。SHA256：`034ad54a3a8495d05a9889fb092b45d17ff4f52a0370fb5402c004ad436b3ea9`。

## 检查与复现

实际结果见 [Batch 2 QA](batch-02-qa.md)，证据目录 `reports/ui-redesign/2026-10-15/batch-2/`。沿用项目已安装工具、独立 3106 端口、本机 Chrome 和现有 Mock API，不安装依赖。

```powershell
# 在 frontend 中，使用已可执行的 Node 环境
node node_modules/eslint/bin/eslint.js . --ext .ts,.tsx
node node_modules/typescript/bin/tsc --noEmit
node node_modules/@rstest/core/bin/rstest.js run
# 构建与浏览器服务使用原 auth-disabled 软件测试模式
$env:SKIP_ENV_VALIDATION='1'
$env:DEER_FLOW_AUTH_DISABLED='1'
node node_modules/next/dist/bin/next build
node node_modules/@playwright/test/cli.js test --config playwright.ui-redesign.config.ts ui-redesign-shell.spec.ts sidebar.spec.ts scheduled-tasks.spec.ts
```

截图环境变量 UI_SHELL_DIR、UI_BASELINE_DIR 以及组件预览 FOUNDATION_PREVIEW_PATH 均指向本批证据目录；TEST_REPORT_DIR 为不同轮次分配独立报告。

旧 sidebar.spec.ts 的通用 Agents 断言与单一星羲产品规则不符，本批更新为星羲助手和隐藏广场的断言；移动欢迎语改为实际的 Xingxi／星羲弦沚。48px 旧尺寸改为设计要求的 64px，尺寸读取改为等待动画稳定后的轮询，并计入侧栏 1px 边框，保留原拖拽／撤销／失焦语义断言。定时任务导航断言改为稳定 href，以适配新的中文导航文案。

首轮检查发现原 Sidebar 和设置弹窗以受控方式开启、没有 Radix Trigger 时，Esc 关闭不能自动返回按钮。手机侧栏在业务组合层使用 BusinessSheetContent 并补上 onCloseAutoFocus，设置弹窗增加可选 restoreFocusRef；未手改生成组件，键盘焦点锁定继续由 Radix 负责。

完整地图定位检查还依赖 PLAYWRIGHT_BASE_URL 计算浏览器权限 origin，必须与隔离入口一致：`$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3106'`。未设置时旧用例会向 localhost:3000 授权，本轮保留首轮失败证据并以正确 origin 补测，未改动定位产品代码。
