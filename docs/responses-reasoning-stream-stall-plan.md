# Responses Reasoning Stream Stall Plan

## 问题概述

OpenAI-compatible Responses API 在高 reasoning effort 下可能长时间只返回 reasoning 事件，而不返回可见正文。用户看到的现象是：

- 发送 message 后先等待一段时间才显示“深度思考中”。
- 切到后台或切屏后，页面更容易回到“正在等待模型回应”。
- 切回来可能出现 `Failed to fetch`。
- 后端日志显示上游已经返回 `200 text/event-stream`，但流里持续是 `has_content=False has_reasoning=True`。

这不是单纯前端显示问题。后端确实把 reasoning-only 阶段当成了不健康流：

- `CHAT_STREAM_IDLE_TIMEOUT=120` 会在 reasoning 阶段超过 120 秒无新 chunk 时触发 `stream_idle` 自动重试。
- `CHAT_COMPLETION_NO_VISIBLE_OUTPUT_TIMEOUT=180` 会在 180 秒内没有可见正文时触发 `visible_output` 超时。
- 自动重试和空响应判断此前只把可见正文、文件、工具调用当成有效输出，没有把 reasoning 块当成防重试信号。

结果是：模型仍在深度思考或只输出 reasoning 信号时，后端可能自动重试、最终标记超时，并把消息保存为 `done=true + error`，前端随后显示失败或等待状态。

容器日志是 UTC，需要换算为北京时间 `+08:00`。例如 `2026-06-20 13:44:33 UTC` 对应 `2026-06-20 21:44:33 +08:00`。

## 已执行修复

本次后端修复聚焦 Responses reasoning-only 流：

1. 新增 `CHAT_STREAM_REASONING_IDLE_TIMEOUT`，默认 `600` 秒。
2. 一旦当前流已经收到 reasoning 信号且还没有可见正文，后续读取上游 chunk 使用 reasoning idle timeout，而不是普通 `CHAT_STREAM_IDLE_TIMEOUT=120`。
3. Responses reasoning 请求的 aiohttp `sock_read` timeout 同步放宽到不小于 `CHAT_STREAM_REASONING_IDLE_TIMEOUT`，避免底层 HTTP 客户端先于业务层断开。
4. 一旦 reasoning 块已经创建，`CHAT_COMPLETION_NO_VISIBLE_OUTPUT_TIMEOUT` 不再因为“没有可见正文”中止流。
5. reasoning 块会阻止空输出自动重试，避免把真实深度思考当成 empty response。
6. 最终空响应判断排除 reasoning-only 内容，避免正常 reasoning-only 阶段被标成空响应错误。

## 可执行验证计划

### 1. 静态验证

```bash
python3 -m py_compile backend/open_webui/env.py backend/open_webui/routers/openai.py backend/open_webui/utils/middleware.py
```

期望：命令无输出、退出码为 0。

### 2. 后端部署验证

如果使用当前 Docker bind mount 后端代码，重启应用容器即可加载 Python 代码：

```bash
docker restart halowebui
docker logs -f halowebui
```

期望：

- 容器恢复 `healthy`。
- 无 Python import / syntax error。

### 3. 深度思考流验证

使用启用 Responses API 且带 reasoning 的模型发送高 reasoning effort 消息。

观察日志：

```bash
docker logs --since 20m halowebui 2>&1 | rg "CHAT REQUEST|UPSTREAM REQUEST|UPSTREAM RESPONSE|STREAM EVT|CHAT AUTO RETRY|visible_output timeout|reasoning_idle|stream_idle"
```

期望：

- 能看到 `has_reasoning=True` 的 stream event。
- reasoning-only 阶段超过 120 秒时不再触发 `CHAT AUTO RETRY reason=stream_idle`。
- reasoning-only 阶段超过 180 秒时不再触发 `visible_output timeout after 180s`。
- 如果超过 `CHAT_STREAM_REASONING_IDLE_TIMEOUT` 仍无新 chunk，才应触发 `reasoning_idle` 超时。

### 4. 切屏恢复验证

在深度思考中切到其他应用或浏览器标签，等待 2-4 分钟后切回。

期望：

- 后端上游流不因 120/180 秒规则被中止。
- 前端即使 socket/fetch 重连，也能从保存的 reasoning 内容或进行中状态恢复，不应立即显示 `Failed to fetch`。

### 5. 回归验证

普通非 reasoning 模型仍应保留原有卡死保护：

- 首个 SSE data 超过 `CHAT_STREAM_START_TIMEOUT` 后超时收束。
- 普通流两个 data chunk 间隔超过 `CHAT_STREAM_IDLE_TIMEOUT` 后超时收束。
- reasoning 流一旦开始输出可见正文，后续也恢复普通 `CHAT_STREAM_IDLE_TIMEOUT` 保护。
- 已有可见正文后上游断流，仍应保留已有内容并结束消息。

## 后续建议

- 前端可继续增强重连恢复：当当前 assistant 有 reasoning 块但无可见正文时，显示“深度思考中”，不要退回“正在等待模型回应”。
- 运行环境可按模型特性调整 `CHAT_STREAM_REASONING_IDLE_TIMEOUT`，建议 600-900 秒。
- 如果上游代理本身会在后台标签页断开 websocket，需要另行检查 nginx/socket.io 心跳与前端重连策略。
