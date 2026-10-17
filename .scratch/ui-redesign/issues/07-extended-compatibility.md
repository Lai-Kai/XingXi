# 07 — Batch 3 扩大检查的历史与图谱兼容用例

Status: needs-triage

Owner: 待分配

Batch 3 扩大检查有 6 项失败，Batch 2 没有这些用例的通过／失败基线。Batch 4 的两项图谱用例已适配专业入口／保留中心并通过；余下 4 项历史用例仍未重跑。

- 已恢复：`knowledge-graph.spec.ts` 2 项，Batch 4 保留所有关系／深度／出处断言，进入 manage 工作台并核对最近中心；最终通过。
- `thread-history.spec.ts` 4 项：1 项等待旧侧栏 `/workspace/chats/new` href；3 项等待 `how can i assist you`，未到达当前星羲输入框。需适配当前导航／文案及可用模型夹具，保留历史隔离／重置／删除断言后重跑。

Batch 4 新证据：reports/ui-redesign/2026-10-15/batch-4/summary.json、final-e2e/。

Batch 3 历史证据：reports/ui-redesign/2026-10-15/batch-3/final-e2e/、summary.json；完整说明见 docs/ui-redesign/batch-03-qa.md。

其余 9 项历史、1 项分支、20 项聊天和 7 项 sidecar 用例通过。本批没有为通过这些旧选择器而恢复通用 Agent 广场或改写业务语义。
