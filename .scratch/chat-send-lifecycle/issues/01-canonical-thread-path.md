# 从规范网址同步聊天 ID

Status: ready-for-human

## 证据

宿主 Gateway 日志中 2026-10-17 18:29:55 创建的会话及运行完成成功；前端随后记录 `SidecarProvider.restoreSidecarThread` 读取 null.promise 的未处理异常。静态 new 路由上的 `useParams` 不会因原生 history 切换产生动态参数，旧会话同步 effect 因此清空 ID。

## 实施

`useThreadChat` 从 Next 的响应式 pathname 读取 ID，保留原生 history 的流式会话状态及浏览器新会话判断。回归覆盖空参数、遗留 new 参数、独立消费者、切换会话、新建和删除；浏览器用例覆盖首条发送后继续向同一会话发送。

## 验证

修复前新增单测 4 项失败、2 项通过，复现新建 ID 被 undefined 覆盖。修复后 6 项生命周期回归及相关 API、重连、发送和侧边会话测试共 33 项通过；最终格式化后重跑 6 项生命周期回归全部通过。完整 `tsc --noEmit`、所改 TS 文件 ESLint 和 `git diff --check` 通过。

浏览器连续发送用例已通过 Playwright 用例发现，未实际执行：当前执行环境不能启动可用的服务/浏览器。宿主开发服务日志已出现修复后的热更新与聊天页 200 请求，但尚无修复后新的发送记录，不能据此声称用户页面已验收。

日志：`/tmp/xingxi-chat-red.log`、`/tmp/xingxi-chat-green.log`、`/tmp/xingxi-chat-final.log`、`/tmp/xingxi-chat-tsc.log`、`/tmp/xingxi-chat-eslint.log`、`/tmp/xingxi-chat-e2e-list.log`。
