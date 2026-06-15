# Chat Provider Stuck Investigation

## 背景

现象：模型 provider 不稳定时，用户发送一次 message 后，界面可能长期停在“正在等待模型回应 ..s”。用户还观察到：

- 中途没有自动重试。
- 最近一次发送后，模型 gateway 后台没有看到预期的主 message 调用。
- 之前出现过 HTTP 499 / timeout / disconnect 后不重试。

本次排查只读取代码、容器日志和数据库状态；没有写入业务数据，也没有记录用户消息正文。

## 排查范围

主要检查路径：

- 前端发送与等待状态：
  - `src/lib/components/chat/Chat.svelte`
  - `src/lib/apis/openai/index.ts`
  - `src/lib/components/chat/Messages/ThinkingIndicator.svelte`
  - `src/lib/components/chat/Messages/ResponseMessage.svelte`
- 后端聊天入口与流处理：
  - `backend/open_webui/main.py`
  - `backend/open_webui/utils/chat.py`
  - `backend/open_webui/routers/openai.py`
  - `backend/open_webui/utils/middleware.py`
  - `backend/open_webui/tasks.py`
  - `backend/open_webui/utils/api_key_pool.py`
- 运行态证据：
  - `halowebui` 容器日志
  - `halowebui-nginx` 容器日志
  - SQLite 数据库 `/app/backend/data/webui.db`

## 请求链路

前端发送消息时会先创建空的 assistant 占位消息，并保存到 chat history。随后调用 `/api/chat/completions`。

前端启动请求有 30 秒超时：

- `CHAT_REQUEST_START_TIMEOUT_MS = 30_000`
- `generateOpenAIChatCompletion(..., { timeoutMs: CHAT_REQUEST_START_TIMEOUT_MS })`

后端 `/api/chat/completions` 并不把完整模型输出同步返回给浏览器。它会：

1. 处理 payload、模型解析、工具/文件/联网等前置逻辑。
2. 调用模型 provider。
3. 如果是流式响应，创建后台 task 继续读取 provider 流。
4. 立即返回 `{ status: true, task_id }` 给前端。
5. 后台 task 通过 socket 发送 `chat:completion` 事件。
6. 前端收到 `done: true` 后才把消息标记为完成。

因此，只要后台 task 没退出、也没有发出错误或 done 事件，前端就会继续显示等待状态。

## 关键发现

### 1. 主 provider 请求当前没有总超时

容器环境中：

```text
AIOHTTP_CLIENT_TIMEOUT=
AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST=
```

代码在 `backend/open_webui/env.py` 中把空字符串转换为 `None`。`backend/open_webui/routers/openai.py` 创建 `aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT))` 时，主 provider 请求等价于没有总超时。

影响：如果 provider 或中间反代进入半开状态，既不返回数据也不抛异常，后台 task 可以长期挂住。

### 2. 后台读流没有 idle timeout

`backend/open_webui/utils/middleware.py` 的 `stream_body_handler` 使用：

```python
async for line in response.body_iterator:
```

该循环没有“首 token 超时”或“chunk 间隔超时”。如果 provider 已经返回响应头，但后续一直不发 SSE chunk，也不关闭连接，异常兜底不会执行。

已有兜底只覆盖“抛异常”的情况：`post_response_handler` 捕获异常后会发送 `done: true + error` 并持久化，避免一直卡住。但半开连接不抛异常，所以不会触发该兜底。

### 3. 自动重试不是 message 级通用重试

当前代码里的重试主要有几类：

- API key pool 切 key 重试。
- Azure Chat Completions endpoint fallback。
- native file input cache / RAG fallback。
- native web search fallback 到 Halo 搜索。

普通 provider 不稳定、流式连接半开、上游长时间不产出，不属于这些自动重试场景。

默认 API key pool retry 状态码是：

```text
429, 500, 502, 503, 504
```

不包含：

- `499`
- `524`

因此这些状态默认不会触发 key-pool retry。

### 4. 499 被误分类

历史 499 错误的原始内容是：

```text
Responses API upstream error (499) from api.asxs.top.
Upstream response: {"error": {"message": "client abort request", "type": "invalid_request_error"}}
```

但当前分类逻辑会因为 `invalid_request_error` 把它归为 `request_incompatible`，UI 显示“携带参数与当前接口不兼容”。这不准确。

这类 `499 client abort request` 更接近客户端/代理/上游响应丢失或超时断连，应该优先归为 `upstream_response_lost` 或 timeout/disconnect 类。

### 5. 最近一次主回复在服务端已完成

容器日志时间是 UTC。本地 Asia/Shanghai 时间需要加 8 小时。

最近一次主 chat 的服务端证据：

- `2026-06-14 16:38:23 UTC`：`POST /api/chat/completions` 返回 200。
- `2026-06-14 16:38:32 UTC`：stream summary 显示 `finish_reason=stop`、`content_len=704`。
- SQLite 中对应 chat 当前 assistant message：
  - `done=True`
  - `content_len=704`
  - `has_error=False`

折算为本地时间：主回复在 `2026-06-15 00:38:32 +08:00` 左右已经完成。

### 6. 最近 00:46-00:47 的 provider 调用更像后处理任务

在主回复完成后，日志中还有：

- `2026-06-14 16:46:52 UTC` 上游请求。
- `2026-06-14 16:47:15 UTC` 上游响应。
- `2026-06-14 16:47:15 UTC` 又发起一次上游请求。
- `2026-06-14 16:47:20 UTC` 上游响应。

这些发生在主回复完成数分钟后，更符合 title / tags / follow-up 等后台后处理模型调用，而不是主 message 调用。

这解释了“gateway 后台没看到最近一次主 message 调用”的一种可能：用户看到的时间点可能对应后处理或页面刷新，而不是新主消息请求。

### 7. 历史中存在 unresolved 空 assistant

在最近 200 个 chat 中找到 2 个历史遗留空 assistant：

- `done` 不是 `true`
- content 为空
- 无 error
- 无可见文件

这说明“空占位消息没有被正确收束”的问题确实发生过。当前最新主 chat 没有这个状态。

## 造成卡住的机制

典型路径如下：

1. 前端创建空 assistant，占位消息进入 history。
2. 后端创建后台 task 读取 provider 流。
3. 前端收到 task id，进入等待状态。
4. provider 或反代不稳定：
   - 未返回响应头；
   - 返回响应头后不再产出 SSE chunk；
   - 中途半开但不抛异常；
   - 客户端/代理超时导致 499；
   - Cloudflare / gateway 返回 502 或 524。
5. 如果异常没有被抛出，后台 task 不结束。
6. `/api/tasks/chat/{chat_id}` 仍可能显示有 active task。
7. 前端 watchdog 认为仍有任务在跑，继续显示等待。
8. 没有通用 message 级 retry，因此不会自动重发。

## 为什么不能简单自动重试所有失败

对流式模型请求来说，自动重试有重复计费和重复执行风险：

- 如果请求已经到达上游，但结果在回传 HaloWebUI 前断开，重试可能重复扣费。
- 如果已经收到部分 token、工具调用、文件或图片，重试可能产生重复副作用。
- `499 client abort request` 可能代表浏览器/代理主动断开，也可能是上游 gateway 把断连包装成 499，需要按具体 gateway 语义判断。

因此自动重试应只在“确认没有任何可见输出、没有工具/文件副作用”的情况下有限执行。

## 当前判断

根因不是单一 provider 报错，而是：

1. 主模型请求缺少后端总超时或流式 idle timeout。
2. 后台 task 挂住后，前端会持续认为消息仍在生成。
3. 自动重试范围过窄，不覆盖普通 provider 半开、499、524。
4. 499 分类错误，导致用户看到错误方向不准确。
5. 后处理模型调用和主回复调用日志混在一起，容易误判 gateway 侧是否收到主 message。

