# 分开检索命中、来源评级与复核状态

Status: ready-for-human

## 实施

修改星羲提示词、搜索工具说明及证据后处理，去掉低等级/未评级一律无记载的开头。保留回答和引用，按实际引用片段追加简短评级/复核/争议说明。空结果保留背景回答并加本地核验限制。领域严格消费者保持默认判定，宽松研究模式仍验证相关性。

检索上下文限定于当前可见用户轮次，避免旧证据抵消新一轮未命中。今日选题沿用工具已核验的绑定检索词。增加两个入口自动提交的浏览器回归用例。

## 验证

首轮新增/调整用例修复前 9 项失败；补充的规范选题词与未使用候选回归修复前另有 2 项失败。再补充的分段文本/推理块回归复现了重复正文和丢失正文各 1 项，已修复：只合并可见文字，保留其他内容块。

最终后端相关 86 项、前端入口/会话/选题客户端单测 18 项通过。完整前端 TypeScript、所改前端文件 ESLint、5 个后端文件 Ruff 检查与格式检查、`git diff --check` 通过。新增的两个浏览器入口用例通过 Playwright 用例发现，但本执行环境不能运行浏览器，未声称实际点击验收。

全量后端变更前后均因既有 `deerflow.skills.skillscan.orchestrator` 缺失等问题在收集期报同样 12 项错误，不能报告全量通过。日志见 `/tmp/xingxi-topic-full-before.log` 和 `/tmp/xingxi-topic-full-after.log`；相关最终日志为 `/tmp/xingxi-topic-final-backend.log`、`/tmp/xingxi-topic-frontend-unit.log`、`/tmp/xingxi-topic-tsc.log`、`/tmp/xingxi-topic-eslint.log` 和 `/tmp/xingxi-topic-e2e-list.log`。

只读真实库验证：使用西施选题绑定的 `release-2c7aafe43b4247fa86ab0d6b951590e7` / `chunk-0625e762d386f7873718b935a571c03aca0b4eabf76b91d1e3fd018c569796b9` 及其真实定位、正文与 U/pending 元数据，把示例回答交给新后处理；回答与 citation 保留，未出现“暂无”，结尾为“资料说明：来源尚未评级；引用片段待复核。”。这验证了新规则对真实资料的处理，不代表重新执行线上模型。

宿主后端运行时没有代码热重载，当前执行环境无法重启宿主服务。需在实际运行环境重启 Gateway 后，新建一次选题问答才能使用新规则；旧会话保存的回答不会自动重写。

## Comments

2026-10-17：只读核对原题 Run `a2774c2f-5dbd-419e-97fb-5cdf3afd4679` 及线程 `b2decb0e-57c4-4410-a1a9-dee14f9635a0` 最终 checkpoint。模型已生成有出处的可靠性分析，但最终可见正文仅剩旧固定提示；metadata 的 `message` 仍为旧版“已检索到低等级材料，仅供补充分析”。启动器从本仓库启动 Uvicorn，命令没有 `--reload`。记录的宿主 PID 在当前进程命名空间不可见，健康检查返回 `Operation not permitted`；没有停止或改写宿主服务。

补充可靠性方法提示：年代、版本、作者与转引来源、传说措辞、独立互证，以及地方记忆和亲历史实的区分。两处证据中间件共享 `_message_content.py`，统一保留非文本块并一次替换可见正文。新增引用回归在修改前复现 2 项失败：带推理块跳过校验、多段正文替换重复并残留无效引用；另新增原题在真实 LangChain 中间件图中有/无本地证据的 2 项软件回归。

最终相关测试 90 项通过，所改 6 个 Python 文件 Ruff lint/format 与 `git diff --check` 通过。全量测试前后均为相同 12 项既有收集错误（缺少 `deerflow.skills.skillscan.orchestrator`），日志 `/tmp/xingxi-reliability-{red,final,full-before,full-after}.log`。只读回放该真实 Run 的工具结果及原始模型回答，通过新中间件保留方法正文，去除 4 处无效 Evidence 引用，末尾为“资料说明：来源尚未评级；引用片段待复核。”；报告 `/tmp/xingxi-reliability-replay.json`。回放不调用线上模型，不写业务库，不代表浏览器验收。状态继续为 `ready-for-human`，剩余仅宿主服务激活与在线验收；已提供确切命令及原题验收说明 `docs/xingxi-answer-policy-activation.md`。
