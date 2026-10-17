# Batch 3 — 核心业务页面

本批按用户 2026-10-15 指定的三个页面实施：检索首页、星羲聊天和古舆地图。设计依据为 Gemini v1.1.0。文献库、图谱及其他页面的完整重构继续留在后续批次；不因共用 Evidence 组件更新而将文献库标为完成。

## 页面与功能对应

| 页面 | 新表现层 | 保留的业务行为 |
| --- | --- | --- |
| `/workspace` | 水墨 Hero、研究 Composer、方向标签、双列选题卡、日期筛选、加载骨架 | 今日／历史 feed、午夜刷新、缓存／本地来源降级、偏好与投票、课题 prompt 与文献／Evidence 范围参数 |
| `/workspace/chats/*` | 最大 880px 对话流、回合题签、真实引文计数、桌面 380px 考据栏、平板 420px 抽屉、手机 65dvh 底部抽屉 | 原消息／工具流、模型选择、停止、历史、分支、附件、人工输入、goal／compact、产物与 sidecar |
| `/workspace/map` | 全屏原色 OSM、浮动工具栏与时间轴、纪年滑块、380px 地点研习面板、移动底部详情 | 目录缓存、定位、路线、图层与不确定范围、逐事件播放、审核／来源、7 个精确绑定 GLB、固定 28/44px 标点 |

## 资产

`frontend/public/brand/xingxi-misty-landscape.jpg` 原样复制自 Gemini 已交付的 `xingxi_xianzhi_hero_banner_1792033797050.jpg`。`ResearchHero` 使用本地 Next Image，图片失败时保留主题底色、标题与可用 Composer。原型和设计文档未改。

## Evidence Inspector

- `EvidenceInspectorProvider` 位于 canonical 聊天页的现有 Artifacts／Sidecar provider 内，仅拥有表现层开关与当前出处。与产物／sidecar 面板互斥，消息和研究输入仍由原组件管理。
- 正常点击引文在原对话打开出处；链接保留 `/workspace/library?evidence_id=...`，修饰键／新标签页及无 Inspector 的其他页面保留导航语义。
- `rehypeEvidenceLinks` 在标准 Markdown URL 过滤前，仅把 `evidence://` 锚点转换为既有站内出处路径。代码、图片和其他协议不放宽，`javascript:` 仍被原过滤器阻止。
- 复用 `getEvidenceDetail`，显示真实书名、版本、卷目、页／叶、来源等级、复核状态、章节、摘录和受保护原件链接。重试与切换出处会取消旧请求，迟到响应不会覆盖当前出处。
- 现有 EvidenceDetail 接口没有独立 Release ID 或 OCR 切片影印字段。本批显示接口已有原文摘录并链接原件，不虚构版本、影印图或原型中的置信度百分比。
- 手机抽屉支持滚动、下拉手柄、关闭／Esc 与焦点返回；原文在书名后优先呈现。桌面关闭也返回发起引用。

## 地图与模型

- 底图与 attribution 保持原样。页面测量浮动工具栏、时间轴、右面板的尺寸，向 MapLibre 传入 camera padding，使初始框选和逐点／逐事件定位落在未遮挡区域；Canvas 仍铺满工作区。
- 纪年滑块使用原生 range，支持键盘、全部年代复位和前后事件，操作复用已缓存目录。旧朝代带、同年事件分组、播放／暂停继续保留。
- 地点保留「沿革」「来源」，新增「关联人物」，只从当前点位已有事件参与者与人物关系生成列表，不从名称推断人物或坐标。
- 3D 页签显示实际文件大小；新增自动旋转，复位同时停止旋转。放大移动原有 model-viewer 元素，关闭／切点／布局切换仍释放旧资源。来源、许可和生成示意提示继续可查。
- 粗指针下的引用、地图缩放与模型 Portal 控件提供至少 44px 热区；模型徽标圆仍固定 28px。触控浏览器专项验证尺寸和实际 tap，实体手机另行验收。

## 文件边界

新增研究 Hero、Evidence provider/context／Markdown 适配器／回合题签、时间轴控件与 `xingxi-research.css`。修改三页、业务引用及消息组合、地图展示层、相关测试。没有修改 `src/core`、后端、API、依赖清单、锁文件、生成的 `ui/` 与 `ai-elements/`，也没有发布或提交。

实际检查、问题修正和限制见 [Batch 3 QA](batch-03-qa.md)，页面见 [截图预览](../../reports/ui-redesign/2026-10-15/batch-3/index.html)。
