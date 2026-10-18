# 问答规则生效检查

本机使用 `/data/laikai/heikesong/deerflow-native/start.sh` 从 `/data/laikai/deer-flow` 启动服务。已核对启动器的 Gateway 命令：单进程 Uvicorn，没有 `--reload`。因此后端源码修改不会自动生效，浏览器刷新也不能替代后端重启。

2026-10-17 的原题“怎样判断地方文献中西施与吴地联系的记载是否可靠？”已有真实检索和模型分析，但最终 checkpoint 仍保存旧版 `low_grade_only` 提示。旧处理遇到 Responses 推理块时未读取正文，随后把可见内容替换成固定提示。这不是检索没有文献。新源码保留可见正文，在末尾说明实际资料限制，并对同样的内容块执行引用校验。

## 在服务器普通终端启用

当前问答结束后执行以下命令。`stop` 会停止此启动器管理的 Gateway、前端和 Nginx，`start` 沿用原配置与现有 SQLite 数据启动，并依次检查 HTTP 就绪状态。

```bash
bash /data/laikai/heikesong/deerflow-native/start.sh stop
bash /data/laikai/heikesong/deerflow-native/start.sh start
bash /data/laikai/heikesong/deerflow-native/start.sh status
```

此命令针对已经核对的本机原生部署；其他部署使用各自的服务管理方式。当前编码环境与宿主进程、网络隔离，无法访问宿主 PID，访问 `127.0.0.1:8001/health` 返回 `Operation not permitted`，不能在这里完成重启或声称线上验收通过。

## 停止后仍报 8001 占用

先在服务器终端检查监听状态：

```bash
ss -ltnp 'sport = :8001'
ss -tan 'sport = :8001'
```

若没有 LISTEN 记录而存在 TIME-WAIT，旧服务可能已正常退出，只是连接仍在回收。旧启动器预检直接 bind，没有设置 `SO_REUSEADDR`，因此会把该状态也报成端口占用。连接回收完成后可直接再次执行 `start`。

仓库提供一行修正，使预检与 Uvicorn 一样允许地址复用。它仍会实际 bind/listen，真实监听进程和权限错误继续阻止启动。启动器目录在当前编码环境可写范围之外，需在服务器普通终端应用；以下命令保留旧文件备份，补丁已应用或上下文不匹配时不会再次修改：

```bash
patch --batch --backup --version-control=numbered --forward --fuzz=0 -p1 \
  -d /data/laikai/heikesong/deerflow-native \
  -i /data/laikai/deer-flow/docs/patches/native-launcher-reuseaddr.patch
bash /data/laikai/heikesong/deerflow-native/start.sh start
```

若 `ss` 显示 LISTEN，按其 PID、程序名和所属部署确认端口归属，再使用该服务的管理入口停止。该补丁不会关闭任何进程，也不会处理已有监听。

补丁的 4 项离线回归覆盖旧预检误报、三个服务端口的地址复用、已有监听仍被拒绝，以及权限错误仍可见；它们在临时目录使用合成 socket 行为，不代表宿主网络验收。

## 在页面验收

1. 刷新页面，新建问答，再问原题。已保存的旧回答不会自动重写。
2. 回答应先说明如何核对成书年代、版本、作者和转引来源、传说措辞，以及独立文献和实物互证。应区分地方故事的流传与人物亲历两种结论。
3. 引用具体材料时应保留有效出处；U 表示未评级，pending 表示片段待复核。相关状态可在末尾简短提示，不应替换正文或成为统一拒答开头。
4. 没有相关本地材料时仍应提供可操作的判断步骤，说明具体史实尚未核验；不得伪造文献或引用。

软件回归使用合成模型返回值检查正文保留、引用清理和状态说明，不等同于真实模型与浏览器验收。
