# Chat Auto Retry Error Emission Plan

## 背景

当前聊天流式响应在上游 Responses/API 返回可重试错误时，存在一个不合理的用户体验：

1. 后端先通过 `chat:completion` 事件把 `error` 发给前端。
2. 前端立即把该错误写入当前 assistant message。
3. 后端随后才在流结束后的自动重试逻辑中判断该错误可重试，并发起下一次请求。

结果是用户会先看到报错，再看到系统自动重试。对于“首个可见输出前”的可重试失败，这个顺序不应该发生。正确行为应是：如果还有自动重试机会，只发 `chat_auto_retry` status，不发 `chat:completion.error`；只有最终失败或不可重试时才展示错误。

## 目标

- 自动重试期间不向前端暴露中间错误。
- 保留 `chat_auto_retry` 状态事件，让前端可以显示“正在自动重试”。
- 自动重试成功后不残留旧错误状态。
- 自动重试耗尽、不可重试、或已有输出后失败时，仍按现有逻辑发送最终错误并持久化。
- 不改变已有“已产生内容后不自动重试”的安全策略，避免重复计费和重复副作用。

## 涉及位置

- `backend/open_webui/utils/middleware.py`
  - `_has_retry_blocking_output`
  - `_is_retryable_api_error_payload`
  - `stream_body_handler`
  - `run_stream_with_auto_retry`
  - final completion/error emission block
- `src/lib/components/chat/Chat.svelte`
  - `chatCompletionEventHandler`
- `backend/open_webui/test/unit/test_stream_api_error_payloads.py`

## 当前问题链路

1. `stream_body_handler()` 解析上游 SSE。
2. 当 SSE data 没有 `choices` 但包含 `error` 时，代码会：
   - 设置 `_stream_api_error`
   - 立即发出：

```python
await event_emitter({
    "type": "chat:completion",
    "data": {"error": error},
})
```

3. 前端 `chatCompletionEventHandler()` 看到 `data.error` 后马上写入 `message.error`。
4. 流结束后，`run_stream_with_auto_retry()` 才调用 `build_retryable_empty_stream_reason()`。
5. 如果判断可重试，再调用 `create_retry_response()` 发起重试。

这个顺序导致“先报错，后重试”。

## 修复方案

### 1. 中间错误只缓存，不立即发给前端

在 `stream_body_handler()` 处理 `not choices` 且 `data.error` 的分支中，删除或改造立即发送 `chat:completion.error` 的逻辑。

建议行为：

- 总是记录 `_stream_api_error = error`。
- 如果当前还没有 retry-blocking output，不立即 emit error。
- 如果已经有 retry-blocking output，则允许按现有最终错误路径处理，但仍不建议在中间流事件里提前 emit error，避免同一错误被发送两次。

建议改为：

```python
if error:
    _stream_api_error = error
```

让最终是否发送 error 统一交给 `run_stream_with_auto_retry()` 之后的 finalization 逻辑。

### 2. 自动重试前只发送 `chat_auto_retry` status

保留 `create_retry_response()` 中的 `emit_auto_retry_status()`。

当 `attempt < auto_retry_max_attempts` 且 `build_retryable_empty_stream_reason()` 返回 reason 时：

- 调用 `emit_auto_retry_status(done=False)`。
- 按 backoff 等待。
- 发起 retry。
- 不发送 `chat:completion.error`。
- 不持久化中间错误。

### 3. 重试成功后清理旧错误状态

后端当前只要中间错误不 emit，前端理论上不会产生旧错误。为稳妥起见，成功恢复时的 status 仍保留：

```python
await emit_auto_retry_status(..., reason="recovered", done=True)
```

前端无需新增逻辑也可以工作。但如果前端曾经从旧版本或竞态收到错误，建议后续可加防御：

- 当同一 message 收到新的 `content` 或 `choices` 时，若 message 仍处于 streaming 且没有 `done` error，可清理 transient retry error。

该前端防御不是本次后端修复的必要条件。

### 4. 最终失败才发送 `chat:completion.error`

当以下任一条件满足时，才允许发送并保存 error：

- 已达到 `CHAT_COMPLETION_AUTO_RETRY_MAX_ATTEMPTS`。
- 错误不可重试。
- 已有可见正文、reasoning、tool_calls、code_interpreter、文件或图片输出。
- retry 返回非 streaming response。
- retry 过程中出现新的不可恢复异常。

最终错误仍由现有 finalization 路径构造：

- `_build_api_error_payload(...)`
- `_build_stream_timeout_error_payload(...)`
- `completion_payload = {"done": True, "error": error_payload, ...}`
- `upsert_response_message(completion_payload)`
- emit `chat:completion`

### 5. 统一错误 emit 归口

将流中所有“提前 emit error”的路径审一遍，原则是：

- 流中可以缓存诊断信息。
- 流中可以 emit `usage`、普通 content、status。
- 流中不要 emit transient `chat:completion.error`。
- 最终只有一个位置负责发送 `done: true + error`。

重点检查：

- `not choices` + `data.error`
- 非 SSE 错误行收集
- HTTP >= 400 且无 structured SSE error
- `ChatStreamTimeoutError`

## 测试计划

### 1. 新增单元测试：可重试 API error 不提前 emit error

在 `backend/open_webui/test/unit/test_stream_api_error_payloads.py` 增加测试：

场景：

- 第一次 stream 返回 SSE error，例如 HTTP 524 或 error family timeout。
- 没有 content、reasoning、tool_calls、files。
- `CHAT_COMPLETION_AUTO_RETRY=True`
- `CHAT_COMPLETION_AUTO_RETRY_MAX_ATTEMPTS=2`
- 第二次 retry 返回正常 content。

断言：

- retry 发生一次。
- events 中包含 `status.action == "chat_auto_retry"`。
- retry 成功前没有任何 `chat:completion` event 携带 `error`。
- 最终 `done=True`，`content` 是 retry 后内容。
- 最终 event 不包含 `error`。
- upsert payload 中不保存第一次中间 error。

### 2. 新增单元测试：重试耗尽后才 emit error

场景：

- 第一次和第二次都返回可重试空错误或 timeout。
- max attempts 为 2。

断言：

- 第一次失败不 emit `chat:completion.error`。
- 只发送一次或多次 `chat_auto_retry` status。
- 最后一次失败后，最终 `done=True + error` 被 emit。
- error 被持久化。

### 3. 新增单元测试：已有输出后不自动重试

场景：

- 第一次 stream 已经返回 content 或 reasoning。
- 随后上游返回 error 或 idle timeout。

断言：

- 不触发 retry。
- 最终保留已有内容。
- 最终 error 正常发送或按现有 partial-output 逻辑收束。

### 4. 前端回归检查

验证 `Chat.svelte` 的 `chatCompletionEventHandler()` 不需要依赖中间 error：

- 收到 `chat_auto_retry` status 时不应修改 `message.error`。
- 收到 retry 后 content 时正常更新 message content。
- 只有最终 `chat:completion.error` 才显示错误。

## 手动验证步骤

1. 启动后端和前端。
2. 使用 Responses API 模型构造首包前 transient error 或通过测试 mock 模拟 524/timeout。
3. 观察前端：
   - 不应先显示红色错误。
   - 应显示或至少收到自动重试状态。
   - retry 成功后正常展示回答。
4. 观察日志：
   - 有 `[CHAT AUTO RETRY] attempt=2/2 reason=...`
   - 没有在 retry 前持久化中间 error。
5. 让 retry 也失败：
   - 最终才显示错误。
   - message 状态为 `done=true`，不会卡在等待中。

## 风险与注意事项

- 不要把已有输出后的错误吞掉。已有输出后失败不能自动重试，仍要收束消息。
- 不要隐藏最终失败。自动重试耗尽后必须发 `done=true + error`。
- 不要扩大自动重试范围。本修复只调整“可重试时不要提前报错”的 emit 时序。
- 不要改变默认重试次数和状态码，除非另有产品决策。
- 如果未来要让前端展示更明确的自动重试提示，应走 status event，而不是 message error。

## 验收标准

- 首个可见输出前的可重试 Responses/API error，不再先显示错误。
- 自动重试期间只发 `status.action = "chat_auto_retry"`。
- retry 成功后最终消息无 `error`。
- retry 失败耗尽后最终消息有准确 `error`。
- 现有 timeout、empty response、reasoning-only stream 相关测试通过。
- `git diff` 仅包含本修复相关后端逻辑、测试和必要文档。
