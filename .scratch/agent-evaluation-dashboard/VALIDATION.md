# 独立评测大盘验证

日期：2026-10-02。范围：前端独立导航、真实 API 大盘、抽屉与文档；未改动评测后端或数据库。

## 已验证

- `cd frontend && pnpm check`：通过。现有 `graph-overview.tsx` 有 4 条 Hook 警告，没有错误。
- `tsc --noEmit`：通过。
- 修改文件的 Prettier 检查及 `git diff --check`：通过。
- 5 个新增纯计算用例：通过。包括缺失/无效耗时、分类及缺失记录、预期超时取消通过、组合筛选、事件排序及未完成批次的图表空值。

Rstest 默认启动 Rsbuild 时因 `listen EPERM 127.0.0.1:3000` 无法启动。为实际验证上述纯计算用例，将现有测试、fixtures 与辅助模块用 TypeScript 编译到 `/tmp/xingxi-evaluation-dashboard-tests/`，只替换测试框架导入为 Node `test`/`assert` 的轻量适配器，测试体保持不变。直接运行 `node /tmp/xingxi-evaluation-dashboard-tests/dashboard.test.mjs` 得到 5/5 通过。这不等于完整 Rstest 套件通过。

## 环境阻塞

- `pnpm test` 的相关 4 个单元测试文件：测试框架启动被本地端口监听限制阻止。
- Next.js 开发服务器：`listen EPERM 127.0.0.1:3108`，无法启动页面。
- Playwright：Chromium 启动触发 `sandbox_host_linux.cc` 的 `Operation not permitted` 并退出；没有实际页面验收或截图。报告位于 `/tmp/xingxi-evaluation-dashboard-playwright/`。
- Recharts 不在本地依赖缓存，npm 域名解析失败；实现采用无新增依赖的 SVG 图表，保留悬停、焦点、点击切换批次及文本说明。

新增页面测试覆盖导航、真实指标、Tooltip、组合筛选、预期超时、证据、手机抽屉、空数据、缺失耗时、API 恢复、未完成批次、读写权限以及旧请求不能覆盖新批次；已有取消/重跑/复核/导出回归已迁移到独立页面，人工评测仍在运营中心。

## 在正常环境复验

```bash
cd frontend
pnpm check
pnpm test tests/unit/core/operations/evaluation-dashboard.test.ts tests/unit/core/operations/evaluations.test.ts tests/unit/core/operations/manual-evaluations.test.ts tests/unit/core/auth/business-role-access.test.ts
pnpm test:e2e tests/e2e/agent-evaluation-dashboard.spec.ts tests/e2e/agent-evaluations.spec.ts tests/e2e/manual-evaluations.spec.ts
```

启动业务栈后打开 `http://localhost:2026/workspace/evaluations`。管理员运行核心 6 项并核对真实批次、取消、重跑、抽屉证据与导出；只读治理用户核对查看/导出且无写控件。固定脚本回放只证明运行契约，不证明真实模型质量。
