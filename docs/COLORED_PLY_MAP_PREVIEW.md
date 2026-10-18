# 地图彩色 PLY 预览

> 本文随 `feat/ui-redesign` 导入，其中既有验证记录属于原分支；本次工作区整合结果见[地图分支整合](map-ui-redesign-integration.md)。

## 从本地打开

1. 打开 `http://localhost:2026/workspace/map` 并登录。
2. 选择任意地图点位，打开「三维预览」；有既有 GLB 的点位仍显示原「3D 建筑研习」页签。
3. 在「打开本地 PLY」中选择 `.ply` 文件，例如 `outputs/creatine_sam2_pure_subject.ply` 或 `outputs/cup_sam2_500k_colored.ply`。
4. 文件按实际 vertex 属性分流：RGB/RGBA 点云使用 Three.js Points；Gaussian PLY 使用现有 Spark。

本地文件仅在当前浏览器预览，不上传、不持久登记为该点位的资产。关闭点位或切换页签会释放查看器，重新打开需再次选择文件。有 GLB 时可用「返回点位模型」恢复原预览。

## 色彩与操作

- RGB/RGBA 点云保留逐点 sRGB 颜色，并转换至渲染器线性色彩空间；Alpha 独立归一化。默认实体颜色显示，勾选「使用文件透明度」可启用原文件的 Alpha 混合，避免高斯派生透明度默认让普通点云显得过暗、穿透。
- 支持 ASCII、binary_little_endian、binary_big_endian；颜色属性支持 `red/green/blue`、`r/g/b`、`diffuse_red/green/blue` 和 `diffuse_r/g/b`，Alpha 支持 `alpha`、`a`、`diffuse_alpha`。
- 支持 8/16/32 位整数颜色和浮点颜色（0–1；大于 1 时按 0–255 归一化）。常见产物为 8 位 RGB/RGBA。
- 拖动旋转，滚轮/双指缩放；可复位视角、翻转上下、调节点大小和切换深浅背景。
- 「放大查看点云」将同一个 canvas 移入弹窗，返回后继续使用，不重复下载或复制场景。
- 当前浏览器上限为 256 MiB、500 万点。超限保留原件，需使用桌面工具查看，不抽点冒充完整产物。

普通 RGB PLY 没有 Gaussian 的旋转、尺度、透明度参数，因此按彩色点云显示；其外观细节取决于已有点与颜色。带 Gaussian 属性的混合文件优先使用 Spark，保留原高斯效果。查看参数只影响显示，不修改下载文件。

## 远程任务

管理员「影像重建」中的已完成任务使用相同分流组件。后端结果元数据增加可选 `kind: gaussian | point_cloud` 和对应 `splat_count | point_count`；旧任务仅有 `splat_count` 仍可读。RGB 结果显示「查看彩色点云」及实际点数，PLY 下载和管理员权限保持原协议。

本次没有启动训练，也没有实现 FLUX 多阶段执行编排、资产版本持久登记或普通用户读取管理员远程任务的新接口。未增加 GPU 调度、结构一致性或重绘拒训门禁。

## 验证

本轮日志与截图位于 `reports/integration/2026-10-17/colored-ply/`。浏览器使用已有真实药罐 RGB PLY 和 Bonsai Gaussian PLY，GLB 使用原七个资源；这些文件仅作为显式指定的测试输入，不注入业务目录。详细结果见该目录的验证说明。
