# Batch 0 / Batch 1 实施说明

采用 Gemini `v1.1.0` 的方向 A。设计原文与原型保持不变；本文件记录工程补充、组件用法及验收范围。

## Batch 0：旧版证据

- 基础提交：`111f59dfa07c7c52ad67d7eb435c35cc8db2b385`，分支 `feat/ui-redesign`。
- 报告根目录：`reports/ui-redesign/2026-10-15/batch-0/`。
- 原版源码、包清单、锁文件、设计及原型副本在 `source/`；摘要与环境见 `manifest.json`。
- 默认 Turbopack 构建成功，无需采用旧日志中提到的 Webpack 绕过方式。
- 四组视口：1440×900、1024×768、390×844、360×800。`screenshots-complete/` 共 49 张截图：核心 6 路由的四视口、桌面／手机暗色、11 个次级入口，以及读者／研究者权限导航。
- 截图测试使用真实 Chrome 和现有 Next.js 构建。业务 API 使用测试夹具，覆盖空目录及不可用状态；不是生产业务数据或真实 Gateway 鉴权验收。
- `screenshots/`、`e2e/` 保留首轮采集及失败；补齐采集在 `screenshots-complete/`、`domain-e2e/`，角色时序修正后的结果在 `roles-e2e/`。
- 图谱审核、文献审核、模型查看器及部分旧选择器／跳转存在改造前失败，见 QA 报告与 `.scratch/ui-redesign/issues/04-baseline-regressions.md`。

## Batch 1：实现位置

| 文件 | 职责 |
| --- | --- |
| `frontend/src/styles/xingxi-tokens.css` | 双主题、语义状态色、阴影、动效、表格及触控／reduced-motion 规则 |
| `frontend/src/styles/globals.css` | 引入 Token；中文字体栈、6/10/14px 圆角及原有 `.field` 的主题、焦点和禁用状态 |
| `frontend/src/components/workspace/business-controls.tsx` | 按钮、输入／多行输入、Evidence 胶囊、审核徽章、面板和骨架 |
| `frontend/src/components/workspace/business-surfaces.tsx` | 原生表格、基于现有 Radix 的 Dialog／Sheet 内容包装 |
| `frontend/src/components/workspace/business-page.tsx` | 既有业务标题、状态、加载、空、错误及重试／关闭操作迁移至语义 Token |

生成目录 `components/ui/`、`components/ai-elements/` 没有修改。API、鉴权、审核、发布、流式状态与地图数据逻辑没有修改。

## 工程补充决策

1. **颜色依据**：设计中 OKLCH 为准，HEX 被标注为示意，不把两者当成可混用的两套主色。
2. **深色补全**：保留指定的六项深色基础颜色，补全其余前景、语义状态、输入与侧栏映射。状态色采用完整背景／边框／前景组合，不能只替换主色。
3. **触控目标**：按钮局部规格为 42px，而全局最低为 44px；公共控件在 coarse pointer 下使用至少 44px。紧凑桌面按钮仍为 36px。
4. **输入边框**：设计的 `--border`／`--input` 是浅色装饰边框，无法同时满足控件边框 3:1。保留原值，新增 `--control-border` 用于 `.field`，浏览器实测输入边框对比度。
5. **行为保持**：公共输入仅转发原生属性、ref、验证与事件；不改 Enter／Shift+Enter／IME／提交协议。新按钮默认 `type="button"`，显式 `type="submit"` 才提交；`busy` 禁用重复操作。
6. **审核与证据**：审核文案复用 `reviewLabels`；普通业务状态复用 `getBusinessStatusPresentation`。Evidence 胶囊复用 `evidenceDetailPath`，保留原有深链接，不自行引入新的检索或跳转契约。
7. **表格／弹窗**：表格保留原生 table 语义；键盘可聚焦横向滚动区，不擅自增加选中或分页协议。Dialog／Sheet 继续使用现有 Radix 的焦点锁定、Escape 与焦点返回，调用方仍提供标题／描述。
8. **素材**：设计登记的四张 JPG 在本机存在，但本批不接入页面横幅、品牌或头像。这些属于后续页面批次，不将个人绝对路径引入产品运行代码。

9. **旧页头兼容**：公共页头不强制覆盖调用页面的前景／背景，防止尚未迁移的原生白底按钮在暗色上下文中继承白字。图标与业务反馈使用自身完整 Token 色对。

## 组件接入示例

```tsx
import {
  BusinessButton,
  BusinessInput,
  BusinessReviewBadge,
  EvidenceCapsule,
} from "@/components/workspace/business-controls";

<BusinessInput id="title" name="title" required aria-label="文献标题" />
<BusinessButton type="submit" busy={saving}>保存</BusinessButton>
<BusinessReviewBadge status={record.review_status} />
<EvidenceCapsule evidenceId={evidence.id} title={evidence.document_title} locator={pageLabel} />
```

Dialog／Sheet 包装用于现有对应 Root 下，并配套 `DialogTitle`／`SheetTitle`。不要替换业务回调或错误处理；各页面按后续批次逐步接入。

## 检查与复现

前端本轮使用 bundled Node `v24.19.0` 直接调用已安装的项目依赖，未安装依赖或改锁文件；bundled pnpm 为 11.25.0，不冒充项目指定的 10.26.2。

在 `frontend/`，将 Node 放入 PATH 后：

```powershell
node node_modules/eslint/bin/eslint.js . --ext .ts,.tsx
node node_modules/typescript/bin/tsc --noEmit
$env:FOUNDATION_PREVIEW_PATH = '<绝对报告目录>/foundation-preview.html'
$env:TEST_REPORT_DIR = '<绝对报告目录>/unit'
node node_modules/@rstest/core/bin/rstest.js run
$env:SKIP_ENV_VALIDATION = '1'
$env:DEER_FLOW_AUTH_DISABLED = '1'
node node_modules/next/dist/bin/next build
$env:PLAYWRIGHT_BASE_URL = 'http://127.0.0.1:3106'
$env:TEST_REPORT_DIR = '<绝对报告目录>/browser'
node node_modules/@playwright/test/cli.js test --config playwright.ui-redesign.config.ts ui-redesign-foundations.spec.ts
```

`playwright.ui-redesign.config.ts` 复用已有测试配置，使用本机 Chrome 和独占的 3106 端口启动已构建的前端；不修改默认 E2E 配置或真实服务。需要截图采集时设置 `UI_BASELINE_DIR` 为新的独立目录，运行 `ui-redesign-baseline.spec.ts`。

基础组件浏览器夹具由 SSR 单元测试导出，加载真实构建 CSS；它不是产品路由。原生提交、焦点、触控、对比度和减弱动效通过该夹具验证，错误重试另在真实地图页面验证。

## 后续边界

部分旧页面仍有硬编码浅色，不能据此声称页面整体暗色迁移完成。Batch 2–5 的导航重排、整页布局、图片素材、聊天／地图／图谱专项改造均未开展。完整业务回归与真实 Gateway 验收仍有待处理项，以 QA 报告为准。
