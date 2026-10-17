# 地图创建点位

管理员可在 `/workspace/map` 顶部点击「创建点位」，或从「创建模型」的关联地图点位下方点击同名按钮。

1. 地图进入选点模式，鼠标变为十字；支持拖动、缩放后再点击位置，也可点击已有标记所处的位置。
2. 点击后显示临时标记和命名弹窗，列出选中的 WGS84 经度、纬度。
3. 输入 1–120 字名称并「保存点位」。支持取消、重新选点；失败时保留输入并可重试。
4. 保存后地图出现新标记，刷新页面仍保留。从创建模型进入时会返回模型弹窗并选中新点位。

## 接口与持久化

- `GET /api/map/custom-points`：登录用户读取自建点位。
- `POST /api/map/custom-points`：管理员创建，使用现有 Cookie 登录和 CSRF 中间件。
- 请求字段：`name`、`lon`（-180..180）、`lat`（-90..90）、`request_id`。服务器校验有限坐标、名称长度、空白及控制字符，拒绝额外字段。
- 迁移 `0046_custom_map_points` 新建 `map_custom_points`；Gateway 启动时自动升级。以创建人和请求 ID 唯一约束处理重复保存，同一请求内容不同返回 409。
- 地图前端将独立读取的自建点位合并至显示目录。模型资产服务同时读取这些点位，因此可直接上传 PLY/GLB 或关联重建任务。
- 返回稳定的 `custom-point-*` 和 `custom-place-*` 身份，`record_kind=custom`，名称按文本渲染。自建点位不自动写入知识图谱、Evidence 或已发布 Release。
- 未配置持久数据库时，读取为空，创建返回 503；不会退化为浏览器内临时保存。

## 验证

测试位于 `backend/tests/test_custom_map_points.py`、`backend/tests/test_migration_0046_map_points.py`、`frontend/tests/unit/core/map/custom-points.test.ts` 和 `frontend/tests/e2e/map-create-point.spec.ts`。既有地图与模型流程一起回归，记录见本地 `reports/integration/2026-10-17/create-map-point/README.md`。
