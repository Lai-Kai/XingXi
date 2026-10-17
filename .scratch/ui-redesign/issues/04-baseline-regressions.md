# 04 — 旧版业务浏览器回归失败

Status: needs-triage

Owner: 待分配

## 证据

2026-10-15 Batch 0 原版与 Batch 1 最终对照中，相同 13 项失败、5 项未执行。既有通过项没有新增失败。原始日志、trace 和逐项映射见 `reports/ui-redesign/2026-10-15/comparison.json` 与两轮浏览器报告。

## 待排查

- 图谱 overview 普通用户控件：1 项。
- 图谱 relation 审核状态／列表、失败恢复、无 Evidence、普通用户可见性：4 项。
- GLB 在移动／桌面切换后的 viewer 数量：1 项。
- 研究项目“查看关联证据”入口：1 项。
- 定时任务侧栏入口：1 项，导致 serial 后续 5 项未运行。
- 文献审核 raw／clean、窄屏、知识版本入口：3 项。
- 首页提交后 URL 即时断言、规范入口的 `Cannot read properties of null (reading 'promise')`：2 项。

Mock 不可用的 Agent 评测页还存在旧版与新版一致的 loading 未结束，已通过截图 metadata 标记。

## 排查原则

先区分测试时序、旧选择器／夹具、框架与产品行为；在独立变更中复现并修复，不为了绿色报告削弱权限或审核断言。此待办未在本轮 Batch 0/1 中擅自扩大为业务修复任务。

## Comments

- 2026-10-15 16:15：项目工作区旧文案断言适配后通过，保留项目范围／文献／记录／出处断言。本轮 112 项通过，前批 97 项无退化。该列表仍留 canonical null promise 1 项未重跑；扩展历史 4 项继续在 07 跟踪。详见 closeout-qa.md。

- 2026-10-15 15:40：Batch 4 同组 38 项从 23 通过／15 未通过恢复至全部通过。此前图谱 ordinary 1＋relation 4、文献复核 3 共 8 项已在本批通过；保留审核／权限断言，修正夹具／manage 入口与 hydration 等待。历史列表中项目 1 与 canonical null promise 1 未重跑，不能关闭整个 issue。见 batch-04-qa.md、batch-4/summary.json。

- 2026-10-15 14:20：Batch 3 将首页 URL 断言改为等待实际导航，将 GLB 测试的 Escape 放到嵌套 Dialog 退出动画卸载之后，两项通过。没有据此声称修复对应产品逻辑；同组剩余 10 项失败继续保留。扩大检查新增 6 项无前批对照的失败，独立记录于 07-extended-compatibility.md。原 Batch 2 的 80 项通过项全部保持通过。

- 2026-10-15：建立改前／改后证据对照，仍未确认上述各项根因。
- 2026-10-15 12:47：Batch 2 按设计补齐定时研究任务入口，稳定 href 断言适配中文文案；该项和原 serial 后续 5 项全部通过。其他 12 项旧失败仍存在；没有新增失败。定位授权 origin 配置不一致的首轮失败已以正确隔离地址补测通过，证据见 batch-2/summary.json 和 batch-02-qa.md。
