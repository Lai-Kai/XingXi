# Native 部署的源码发布基线

`scripts/capture_native_release.py` 将服务器当前实际使用的公开源码保存成可校验的私有快照。它记录未提交和未跟踪的代码，不执行 `git add`、`commit`、`reset`、`clean`，也不会切换、重启服务。快照中的 `git.dirty: true` 如实表示部署目录存在未提交修改，不能将它称为干净提交。

## 捕获和验证

以部署目录所有者运行，使用已有的后端 Python。先执行只读预检：

```bash
/data/laikai/deer-flow/backend/.venv/bin/python \
  /data/laikai/deer-flow/scripts/capture_native_release.py \
  --root /data/laikai/deer-flow \
  --host-dir /data/laikai/heikesong/deerflow-native \
  --dist-dir frontend/.next-releases/upload-button-20261021-v2 \
  --database /data/laikai/deer-flow/backend/.deer-flow/data/deerflow.db \
  --check
```

实际构建目录应按当次部署收据填写；工具不读取 `.env` 来猜测当前生产构建。`--dist-dir` 和 `--database` 均可省略，省略后对应元数据为 `null`。

预检通过后，以同样参数去掉 `--check`，增加一个新的发布标识：

```bash
--release-id high-priority-20261023-before
```

默认输出是 `<host-dir>/.runtime/releases/<release-id>/`；新建目录使用 `0700`、文件使用 `0600`。也可使用 `--output /另一个私有目录/新的发布目录`。输出目录必须不存在，且必须在源码仓库外；现有目录的权限、所有权不会被工具重写。Windows 的 Unix mode 不等于 ACL，生产权限检查应在 Linux 上进行。

```bash
/data/laikai/deer-flow/backend/.venv/bin/python \
  /data/laikai/deer-flow/scripts/capture_native_release.py \
  --verify /data/laikai/heikesong/deerflow-native/.runtime/releases/high-priority-20261023-before
```

捕获过程会自动执行同一验证。失败返回非零状态；内容检测只报告文件路径和问题类别，不打印匹配的密钥。预检不创建发布目录；捕获中失败只清理由本次新建的未完成发布目录。

## 交付内容和边界

- `source.tar.gz`：`source/` 内为公开源码，`native/` 内为实际主机的 `launch.py` 与 `nginx.conf.template`，可选的 `build/BUILD_ID` 记录前端构建标识。
- `manifest.json`：Git HEAD、分支和状态；每个实际打包文件的大小、SHA256、可执行位；删除项、排除项；依赖锁文件 SHA256；可选生产 BUILD_ID 与构建清单 hash；可选 SQLite `alembic_version`。它不会读取业务数据。
- `SHA256SUMS`：上述源码包、manifest 和恢复说明的完整性校验。
- `RESTORE.md`：恢复步骤与限制，不自动修改任何部署。

文件候选来自 `git ls-tree HEAD`、`git ls-files --cached` 和 `git ls-files --others --exclude-standard`。因此既记录未暂存删除，也记录已暂存删除、重命名前旧路径和未跟踪源码。默认遵守 `.gitignore`；忽略的运行数据不纳入枚举。所有候选经过明确的公开扩展名白名单，未收录项在 manifest 中说明原因。源码与 Git 状态在打包后再次核对，发现并发修改即失败，请在修改完成后的稳定时间窗口重新捕获。

真实 `config.yaml`、`.env*`（示例除外）、连接配置、密钥、数据库、日志、`.runtime`、`.cache`、`.scratch`、`.deer-flow`、`node_modules`、虚拟环境、前端构建目录等均被排除。工具不保存原始 `git diff`，避免其中混入私密配置。文件内容会拒绝可识别的真实供应商 token 和独立行的私钥块；`EXAMPLE_API_KEY`、`local-dev-secret` 等公开占位文本可保留。这是有限的凭据检测，不能证明任意源码一定不含未知格式的秘密。

快照只恢复 manifest 声明的公开源码。真实配置、数据库、运行素材、SSH 密钥必须单独私下备份；依赖、OS/Python/Node 版本、模型引擎、外部服务和 GPU 环境也需要另行记录。构建 ID/hash 仅证明捕获时观察到的构建标识，不证明现有生产包一定由本次源码构建，更不包含全部生产静态资源。

## 恢复步骤

1. 在可信且只有所有者可写的位置保留发布目录与收据，先执行 `--verify`。SHA256 验证完整性，不验证签名或作者。
2. 创建一个新的独立检出，切到 manifest 的 `git.head`。保留原线上目录供核对和回退。
3. 校验后将档案解到空的私有暂存目录，再将 `source/` 覆盖到新检出。逐项审阅 `deleted_files`，仅在这个新检出中手动处理删除路径。工具本身不执行恢复或删除源码。
4. 单独审阅 `native/` 中主机脚本和模板，恢复私密配置与数据库，按锁文件安装依赖并确认迁移版本。不要把 `build/BUILD_ID` 当成可直接运行的完整前端构建。
5. 在新的构建目录重新构建并验证；实际切换服务和回滚由既有部署流程执行。

验证工具从不解压档案，并拒绝路径穿越、绝对路径、Windows 驱动器路径、重复成员、符号链接、硬链接、未知成员、文件遗漏与 hash/大小不符。捕获也拒绝源码或输出路径经过符号链接，以避免边界被重定向。

离线回归使用临时 Git 仓库，无网络、无服务切换：

```bash
python -m unittest discover -s tests -p test_native_release_capture.py
```
