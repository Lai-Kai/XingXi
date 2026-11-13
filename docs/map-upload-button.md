# 地图重建文件按钮与权限

2026-10-21 已部署至12026。

影像重建面板将原生文件入口改为带上传图标的按钮；悬停抬升2px、点击按压，键盘Enter/Space可唤起原生文件选择器。已选后显示文件名或数量，可重新选择。位移和缩放只在motion-safe启用，减少动态效果时保留静态反馈。Input仍支持多选及服务器extension列表，选择文件不会提交表单；格式、大小、幂等、CSRF与上传进度逻辑不变。

## 权限

- 选择文件：点击后由浏览器原生文件窗口授予本次所选文件访问，不要求Windows管理员、服务器SSH或额外项目授权；不会自行读取本机其他目录。
- 启动重建、读取任务、取消及下载重建产物：后端reconstructions.admin要求登录且system_role=admin；普通用户403，匿名401。按钮不改变权限策略。
- 当前用户通过正常登录实测角色admin，能力/任务接口200。SSH工作账户、专用SFTP权限与FLUX/OOOSplat部署继续由后端使用，不下发浏览器。普通用户无需也不能因改按钮绕过权限。

## 验证边界

22项既有backend/tests/test_reconstructions.py回归通过，含普通用户GET/POST403且不启动remote。ESLint通过，Webpack/TypeScript生产构建退出0。桌面1440×1000及390×844减少动态效果模式的6项浏览器回归通过：点击文件窗口、不误提交、键盘重选、FLUX字段、CSRF及任务取消；提交部分在浏览器层拦截，未启动GPU训练。真实服务器管理员页面另验证古松园选择、原生文件窗口、图片与视频重选、移动端无横向溢出和无页面异常。

临时生产端口13026探测通过并释放，仅切前端。Gateway与Nginx仍沿用原PID，数据库未重启。当前产物为frontend/.next-releases/upload-button-20261021-v2；此前产物保留，私有.env记录当前dist目录。Next生成的目录types includes与gitignore同步保留。修改前源码/配置及构建/切换回执位于宿主.runtime/upload-button-20261021/，其中私有配置不得提交。脱敏报告位于扫描项目outputs/xingxi_upload_button_20261021/。
