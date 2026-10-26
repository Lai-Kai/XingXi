# 地图上传临时空间与准入检查

地图视频/图片重建仍允许最多 2 GiB 素材，已有 PLY/GLB 模型仍允许最多
256 MiB。multipart 请求另留 16 MiB 封装开销；文件实际大小继续由原有
复制逻辑逐块验证。

## Native Gateway 临时目录

`host-deployment/launch.py` 的 `get_gateway_env(env)` 为 Gateway 返回独立的
进程环境，并创建 `DEER_FLOW_HOME/gateway-upload-tmp`。该目录权限为 0700，
拒绝符号链接及其他账户所有的目录。返回环境中的 `TMPDIR`、`TMP`、`TEMP`
均指向此目录；前端与 Nginx 的环境不变。

Python 在首次使用 tempfile 时确定临时路径，因此修改后必须重启 Gateway。
需要单独重启时可复用 `settings()` 的环境，再调用 `get_gateway_env(env)`，
无需通过本启动器停止其他服务。应以部署账户执行，不修改其他用户目录。

## 上传前检查

`MapUploadStorageMiddleware` 只处理两个 POST 入口：

- `/api/reconstructions`
- `/api/map/model-assets`

必须在 `add_middleware(AuthMiddleware)` 之前注册，从而让既有身份与 CSRF
验证在外层先执行。中间件自身也核对管理员身份，再检查存储。FastAPI 的
Form 参数在路由依赖前解析，因此仅在路由函数内检查会晚于临时文件写入。

每次请求按可信上限核算临时副本与持久副本所需空间。有 Content-Length
时采用声明大小；无此字段时按对应入口的最大请求大小核算。长度字段不作为
文件大小校验的替代：接收流仍计数，超过声明值或最大请求量立即返回 413。

两目录属于同一设备时合并两份需求，只读取一次该设备可用空间，并只留一次
512 MiB 余量。不同设备分别核算。进程内并发请求持有独立预算，完成、异常、
取消及检查线程在取消后才返回时均释放预算。空间不足返回 507，正文使用中文
字符串 detail，与现有上传客户端兼容。

`require_persistent_space(root, size)` 在复制前按实际文件总量复查持久空间，
不重复申请同一请求的准入预算。所有文件系统探测均在工作线程调用。

FastAPI 会将 multipart 临时文件写入的 ENOSPC/EDQUOT 包装成 HTTP 400。
Gateway 的 Starlette HTTPException 处理器须结合 `is_storage_exhaustion`
检查异常链，将真实空间不足转换为 507；其他格式错误仍按原状态返回。

该检查是准入判断，并非对其他进程的磁盘配额。其他任务仍可能在检查后写满
磁盘，因此持久复制与异常处理必须保留 ENOSPC/EDQUOT 的 507 转换。
此实现不删除旧训练结果、其他用户文件或系统临时目录，也不新增 GPU 排队。

## 验证

`backend/tests/test_map_upload_storage.py` 使用隔离目录和模拟可用空间，覆盖
同/不同分区、并发预算释放、预解析拒绝、权限顺序、现有容量上限、伪造长度、
线程取消以及 FastAPI multipart 包装异常。`tests/test_native_gateway_temp.py`
只加载启动器的独立环境函数，验证目录与环境隔离，不启动任何服务。
