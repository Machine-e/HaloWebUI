# Chat Provider Stuck Remediation Plan

## 目标

修复目标按优先级排序：

1. 不允许聊天消息无限停在“正在等待模型回应”。
2. 准确区分请求未开始、上游超时、上游断连、请求不兼容。
3. 只在低风险场景自动重试，避免重复计费或重复工具副作用。
4. 让主回复请求和后台后处理请求在日志/状态上更容易区分。

## 短期止血

### 1. 配置主请求超时

建议先给运行环境设置：

```bash
AIOHTTP_CLIENT_TIMEOUT=600
```

如果长回答较多，可设置为 `900`。

作用：避免 provider 请求无限挂住。

代价：这是总超时，极长输出可能被中止。因此这只是止血，不是最终方案。

### 2. 降低后处理压力

provider 不稳定时，建议临时关闭或减少：

- 自动 follow-up generation
- 自动 tag generation
- 自动 title generation
- 高 reasoning effort 的默认配置

原因：主回复完成后这些任务还会继续调用 provider，容易造成 gateway 日志混淆，也会在上游不稳定时放大错误数量。

## 后端修复

### 1. 增加流式 idle timeout

新增配置建议：

```text
CHAT_STREAM_IDLE_TIMEOUT=120
CHAT_STREAM_START_TIMEOUT=120
```

语义：

- `CHAT_STREAM_START_TIMEOUT`：从上游响应开始到第一个有效 SSE data 的最长等待时间。
- `CHAT_STREAM_IDLE_TIMEOUT`：两个有效 SSE chunk 之间的最长等待时间。

实现位置：

- `backend/open_webui/utils/middleware.py`
- `stream_body_handler(response)` 中读取 `response.body_iterator` 的循环。

建议行为：

1. 超时前没有任何可见输出：发送 `done: true + error`，错误类型为 timeout / upstream response lost。
2. 已有部分输出后超时：保留已有内容，标记 `done: true + error`，提示回复被中断。
3. 无论哪种情况，都要：
   - 调用 `response.background()` 或等价清理。
   - 关闭 upstream response/session。
   - 持久化 `done: true`。
   - 清理 task。

这样即使 provider 半开，UI 也不会永久等待。

### 2. 给 aiohttp 设置连接/读空闲超时

不要只依赖 `total`。更稳妥的是在 provider 请求处设置：

- connect timeout，例如 30 秒。
- sock read / stream idle timeout，例如 120 秒。
- 可选 total timeout，例如 600-900 秒。

实现位置：

- `backend/open_webui/routers/openai.py`
- 以及 Gemini / Anthropic / Ollama 兼容路径中等价的流式请求位置。

注意：流式长回答不应只靠较短 total timeout 控制，否则会误杀正常长输出。

### 3. 修正 499 / 524 错误分类

修复位置：

- `backend/open_webui/utils/middleware.py`
- `src/lib/components/chat/Chat.svelte`

建议规则：

- `499` 且 body/message 包含 `client abort request`、`client closed`、`disconnect`、`connection closed` 时，归为 `upstream_response_lost`。
- `524` 归为 Cloudflare / upstream timeout，而不是普通 upstream service error。
- 断连类判断应优先于 `invalid_request_error`、`unsupported parameter` 等请求兼容性关键词。

用户提示建议：

- 499：请求或响应链路被中断，先确认上游是否已产生结果/计费，再决定是否重试。
- 524：Cloudflare 等反代等待 origin 超时，稍后重试或检查上游 origin 健康。

### 4. 扩展 retry 策略，但限制自动重试条件

建议新增 message 级有限 retry，不要直接重试所有失败。

允许自动重试的条件：

- 主回复尚未产生任何可见 token。
- 没有文件、图片、工具调用、代码执行等副作用。
- 没有收到 upstream completion id 或明确 billing signal。
- 错误属于 transient：
  - connect timeout
  - read idle timeout before first token
  - 502
  - 503
  - 504
  - 524
  - 网络连接异常

默认不自动重试或需用户确认的条件：

- 已收到任意 token。
- 已执行工具调用。
- 已产生文件/图片。
- `499 client abort request` 且无法确认未计费。
- `upstream_response_lost` 且上游可能已经完成。

API key pool 默认 retry 状态码可考虑加入：

```text
524
```

`499` 不建议默认加入全局 retry 状态码。更建议按 body 判断，只在确认是未进入模型计算的 gateway 失败时重试。

#### 建议的自动重试策略调整

当前 retry 更接近“API key pool 换 key 重试”，不是“主 message 请求重试”。建议把自动重试拆成两层：

1. **provider/key retry**：仍保留现有 key pool 行为，用于切换同一连接下的可用 key。
2. **message attempt retry**：新增主消息级有限重试，用于 provider transient failure，但必须有副作用保护。

建议新增后端配置：

```text
CHAT_COMPLETION_AUTO_RETRY=true
CHAT_COMPLETION_AUTO_RETRY_MAX_ATTEMPTS=2
CHAT_COMPLETION_AUTO_RETRY_BACKOFF_SECONDS=2,5
CHAT_COMPLETION_AUTO_RETRY_STATUSES=408,429,500,502,503,504,524
CHAT_COMPLETION_AUTO_RETRY_BEFORE_FIRST_TOKEN_ONLY=true
CHAT_COMPLETION_AUTO_RETRY_499=false
```

默认策略建议：

- `max_attempts` 默认 `2`，也就是原始请求加一次自动重试。
- 默认只在首 token 前重试。
- `502/503/504/524` 可以自动重试一次。
- `429` 可以自动重试一次，但应尊重 `Retry-After`。
- `408`、connect timeout、read idle timeout before first token 可以自动重试一次。
- `499` 默认不自动重试；只有 gateway 明确承诺该 499 未进入模型执行/不会计费时，才允许按连接配置开启。

自动重试判定顺序建议：

1. 先判断请求阶段是否已经产生可见输出：
   - token content
   - reasoning content
   - tool call
   - file/image
   - citation/source
   - upstream response id / completion id
2. 如果已有任意输出或副作用，禁止自动重试，只结束当前消息并提示用户手动确认后重试。
3. 如果没有输出，再判断错误是否 transient。
4. 如果是 transient，按 backoff 重试同一主消息请求。
5. 每次重试都记录 `attempt`, `max_attempts`, `retry_reason`, `status`, `provider`, `request_url`。
6. 最后一次失败必须发送 `done: true + error` 并持久化，不允许继续等待。

状态码建议：

```text
408  -> retry before first token
429  -> retry before first token, respect Retry-After
500  -> retry before first token
502  -> retry before first token
503  -> retry before first token
504  -> retry before first token
524  -> retry before first token
499  -> no auto retry by default; classify as response lost / client abort
400/401/403/404 -> no auto retry
```

主回复和后处理任务要分开：

- 主回复可以执行上述 message attempt retry。
- title / tags / follow-up 这类后处理任务不应让主消息重新进入等待状态。
- 后处理任务可以有自己的轻量 retry，但失败后只记录日志，不影响主回复 `done=true`。

实现位置建议：

- `backend/open_webui/main.py`：保留原始 request body，主消息失败后可重建 form data。
- `backend/open_webui/routers/openai.py`：暴露更准确的 transient error / timeout / upstream lost 信号。
- `backend/open_webui/utils/middleware.py`：记录是否已经有可见输出或副作用，并决定是否允许重试。
- `src/lib/components/chat/Chat.svelte`：前端只展示 retry 状态，不在浏览器端直接重发主消息，避免多端重复发送。

### 5. 前端 watchdog 收束卡住状态

修复位置：

- `src/lib/components/chat/Chat.svelte`

建议调整：

1. watchdog 多次恢复失败后，即使 `/api/tasks/chat/{chat_id}` 仍返回 active task，也允许前端调用 `stopTask` 并把当前消息标记为 error/done。
2. 页面恢复时，不要仅因为 chat 有 active task 就把最新 assistant 强制设为 `done=false`。应优先使用 task metadata 的 `message_id` 匹配具体消息。
3. 对空 assistant 占位消息，如果长时间没有内容、没有 error、没有 task progress，应持久化为 `generation_interrupted`，避免刷新后继续卡住。

### 6. 清理已完成消息中的 active status

当前已完成消息里可能仍保留 `tool_orchestration done=false` 等状态，导致消息下方仍显示小 spinner。

建议：

- 后端完成时把 active status 标为 done 或 hidden。
- 前端渲染时，如果 `message.done === true`，不要显示 `done === false` 的 status spinner。

这不是主卡住的根因，但会造成视觉误导。

### 7. 区分主回复和后处理日志

建议给后处理模型调用增加明确日志字段：

```text
task=title_generation
task=tags_generation
task=follow_up_generation
phase=post_response
```

主回复请求也应有：

```text
phase=chat_completion
chat_id=...
message_id=...
```

这样 gateway 侧排查时能区分“用户主消息调用”和“完成后的后台模型调用”。

## 推荐实施顺序

1. 先设置 `AIOHTTP_CLIENT_TIMEOUT=600` 止血。
2. 后端加入 stream start / idle timeout，并确保超时后持久化 `done: true + error`。
3. 修正 499 / 524 分类。
4. 前端 watchdog 支持强制收束卡住消息。
5. 再做有限自动重试。
6. 最后优化后处理日志和 status 清理。

## 验证用例

建议用 fake upstream 覆盖以下场景：

1. 不返回响应头：前端 30 秒启动超时后，消息应落成 error/done。
2. 返回响应头后不发任何 SSE：后端 start timeout 后应结束消息。
3. 已发部分 token 后静默：后端 idle timeout 后应保留部分内容并标记中断。
4. 返回 502 JSON：应显示 upstream transient error，不应无限等待。
5. 返回 524 JSON：应显示 Cloudflare / upstream timeout。
6. 返回 499 + `client abort request`：应归为 response lost / disconnect，不应显示请求参数不兼容。
7. 已收到 token 后断连：不得自动重试，只提示可能已产生计费。
8. 无 token 的 502/503/504/524：最多自动重试一次，并记录 retry reason。
9. 主回复完成后 title/tags/follow-up 失败：不得把已完成主回复重新变成等待状态。

## 成功标准

修复后应满足：

- 没有 chat 可以无限显示“正在等待模型回应”。
- 499 / 524 的 UI 提示方向正确。
- 自动重试不会在已有输出或副作用后触发。
- `/api/tasks/chat/{chat_id}` 中的 active task 不会让已完成消息重新变成未完成。
- 日志能明确区分主回复和后处理调用。
