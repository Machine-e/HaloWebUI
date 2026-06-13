# HaloWebUI Socket 卡住修复计划

## 目标

解决 Web/Android WebView 挂后台后，聊天一直处于生成中、后续消息只进队列但不再发请求的问题。

最终行为要求：

- 页面回到前台或 socket 重新连接后，能及时重新对账当前聊天状态。
- socket 断线时主动重连，并在连接恢复后重新加入用户房间、恢复 chat-events 监听。
- 初始 `/api/chat/completions` 请求、后台 task、聊天保存等关键等待点都有超时兜底。
- 重试多次仍失败或总耗时过长时，把当前 assistant 消息标记为明确错误并释放 `taskIds/messageQueue`，不允许 UI 无限卡住。
- Android WebView 回到前台时触发页面侧恢复，而不是只依赖 socket.io 自己恢复。

## 当前证据

- 前端 socket 建立在 `src/routes/+layout.svelte` 的 `setupSocket`，目前只有 `reconnect_attempt/reconnect_failed` 日志，没有连接状态 store，也没有 reconnect 后的聊天状态恢复。
- 聊天页 `src/lib/components/chat/Chat.svelte` 只在 `loadChat` 时拉 `getChatContextById` 并执行 `reconcileLoadedAssistantMessages`，没有在 `visibilitychange` 或 socket reconnect 后重新拉 `/api/v1/chats/{id}/context`。
- 发送前如果 `taskIds` 非空或最后一条 assistant 未完成，会进入 `messageQueue`，不会发新的 `/api/chat/completions`。如果后台期间丢了 `done` 事件，队列会永久卡住。
- 后端在 `backend/open_webui/utils/middleware.py` 中用 `create_task(..., id=chat_id)` 后台处理 stream，并通过 socket `chat:completion` 推送内容和 done。
- 后端会把最终内容和 `done: true` 写回聊天历史；因此前端可以通过重新加载聊天记录恢复，而不必依赖丢失的 socket 事件。
- 当前工作区已有未提交改动：`Chat.svelte` 已开始按 `messageId -> taskId` 跟踪；`backend/open_webui/tasks.py` 已把停止不存在 task 改为幂等成功。这些应保留并继续完善。

## 修复策略

### 1. 增加全局 socket 连接状态和恢复事件

位置：`src/routes/+layout.svelte`、`src/lib/stores/index.ts`

新增 store：

- `socketConnectionState`: `connected | disconnected | reconnecting | failed`
- `socketReconnectRevision`: number，每次 connect/reconnect 成功递增
- `socketLastConnectedAt` / `socketLastDisconnectedAt`

调整 `setupSocket`：

- 设置 `timeout: 10000`，避免 connect 无限 pending。
- 设置 `reconnectionAttempts: 8`，`reconnectionDelay: 1000`，`reconnectionDelayMax: 5000`。
- `connect` 时：
  - 更新连接状态为 `connected`。
  - 如果已有 `$user` 和 token，重新 `$socket.emit('user-join', { auth: { token } })`。
  - 递增 `socketReconnectRevision`。
- `disconnect` / `reconnect_attempt` 时更新状态，给 UI 和聊天页判断使用。
- `reconnect_failed` 时更新为 `failed`，但不要永久停掉恢复流程；允许前台恢复时显式 `socket.connect()`。

### 2. 前台恢复时主动 reconnect + 当前聊天对账

位置：`src/routes/+layout.svelte`、`src/lib/components/chat/Chat.svelte`

在 layout 的 `visibilitychange` 中：

- 当 `document.visibilityState === 'visible'`：
  - 如果 socket 不存在、未 connected、或状态为 failed，调用 `setupSocket(...)` 或 `$socket.connect()`。
  - 派发 `window.dispatchEvent(new CustomEvent('halo:foreground-resume'))`。

在 `Chat.svelte` 中新增 `recoverActiveChat(reason)`：

流程：

1. 忽略临时聊天、无 `$chatId`、正在切换聊天、重复并发恢复。
2. 拉取 `getChatContextById(localStorage.token, $chatId)`。
3. 拉取 `getChatById(localStorage.token, $chatId)`。
4. 用服务端聊天历史覆盖/合并本地当前聊天历史，优先保留本地已停止状态。
5. 用服务端 `task_ids` 更新 `taskIds`，并执行 `reconcileLoadedAssistantMessages(taskIds)`。
6. 如果服务端没有 active task，而当前 assistant 仍未完成：
   - 如果服务端消息已经 `done: true`，直接更新为完成态。
   - 如果服务端消息仍空且超时，标记错误并 `resetTaskIds()`。
7. 如果恢复后无 pending task 且 `messageQueue` 有内容，释放队列继续发送下一条。

触发点：

- `window` 的 `halo:foreground-resume`。
- `socketReconnectRevision` 变化。
- 发送新消息前发现 `hasPendingTask || hasRunningResponse` 时，先执行一次 `recoverActiveChat('before-send')`，再决定是否 queue。

### 3. 给每个 response task 加 watchdog

位置：`src/lib/components/chat/Chat.svelte`

新增状态：

- `responseTaskWatchdogs: Record<messageId, { taskId, startedAt, lastEventAt, recoverAttempts, hardTimeoutAt }>`

在 `registerResponseTask(messageId, taskId)` 中初始化：

- `startedAt = Date.now()`
- `lastEventAt = Date.now()`
- `recoverAttempts = 0`
- `hardTimeoutAt = startedAt + CHAT_TASK_HARD_TIMEOUT_MS`

建议默认值：

- `CHAT_TASK_SILENCE_TIMEOUT_MS = 90_000`
- `CHAT_TASK_RECOVER_INTERVAL_MS = 30_000`
- `CHAT_TASK_MAX_RECOVER_ATTEMPTS = 3`
- `CHAT_TASK_HARD_TIMEOUT_MS = 10 * 60_000`

在每次 `chatCompletionEventHandler` 或其他 socket 流事件到达时更新 `lastEventAt`。

新增 `runTaskWatchdog()`，用 `setInterval` 每 15 秒检查：

- 如果 socket disconnected 且 silence 超过 30 秒：尝试 `socket.connect()`。
- 如果某个 message silence 超过 90 秒：调用 `recoverActiveChat('watchdog-silence')`。
- 如果恢复次数超过 3 次仍无完成态：
  - 若服务端仍有 task，先 `stopTask(token, taskId)`。
  - 标记 assistant 消息错误：`连接中断或长时间未收到响应，已停止等待。`
  - `done = true`，写 `completedAt`。
  - `clearTaskForCompletedResponse(messageId)`。
  - `saveChatHandler($chatId, history)`。
- 如果总耗时超过 hard timeout：
  - 同样 stop task、写错误、释放队列。

`clearTaskForCompletedResponse` 和 `resetTaskIds` 必须同步清理 watchdog。

### 4. 给初始 completion 请求加超时和可取消

位置：`src/lib/apis/openai/index.ts`、`src/lib/components/chat/Chat.svelte`

`generateOpenAIChatCompletion` 当前直接 `fetch`，没有 timeout。改为支持 options：

```ts
generateOpenAIChatCompletion(token, body, url, { timeoutMs = 30000, signal } = {})
```

实现：

- 使用 `AbortController`。
- `setTimeout(() => controller.abort(...), timeoutMs)`。
- timeout 时抛出结构化错误：`{ type: 'request_timeout', detail: 'Chat request did not start in time.' }`。

`sendPromptSocket` 捕获后：

- 当前 assistant 消息写入 error。
- `done = true`。
- `resetTaskIds()`。
- 不进入无限等待。

### 5. 保存和发送前等待点加软超时

位置：`src/lib/components/chat/Chat.svelte`

发送前仍有可能卡在：

- `saveChatHandler` / `pendingChatSave`
- inline image persistence upload
- memory query
- `getAndUpdateUserLocation`

新增通用 helper：

```ts
withTimeout(promise, timeoutMs, label)
```

应用：

- `saveChatHandler`：软超时 15 秒。超时后提示保存失败但允许继续发 completion；后续后台再补保存。
- `queryMemory`：软超时 10 秒。失败则跳过 memory，不阻塞发送。
- `getAndUpdateUserLocation`：软超时 5 秒。失败则跳过 location。
- inline 图片持久化上传：单张 20 秒，总体 60 秒。失败保留原引用，不阻塞模型请求。

原则：非必要上下文增强不能阻塞主请求无限等待。

### 6. Android WebView 前后台配合

位置：`android/app/src/main/java/com/halowebui/android/MainActivity.java`

新增 `onResume`：

- `webView.onResume()`。
- `webView.resumeTimers()`。
- `evaluateJavascript("window.dispatchEvent(new CustomEvent('halo:android-resume'))", null)`。

新增 `onPause`：

- `webView.onPause()`。
- 不建议调用全局 `pauseTimers()`，它会影响 WebView 内 socket.io 心跳和恢复时序。

前端监听 `halo:android-resume`，复用 `halo:foreground-resume` 的恢复逻辑。

### 7. 后端补充状态可观测性

位置：`backend/open_webui/tasks.py`、`backend/open_webui/main.py`

在 task metadata 中记录：

- `created_at`
- `updated_at`
- `message_id`
- `blocks_completion`

`/api/tasks/chat/{chat_id}` 返回结构从仅 `task_ids` 扩展为兼容格式：

```json
{
  "task_ids": ["..."],
  "tasks": [
    { "id": "...", "created_at": 123, "updated_at": 456, "blocks_completion": true }
  ]
}
```

前端继续兼容旧字段 `task_ids`。

### 8. 错误文案和用户可见行为

新增统一错误：

- 请求启动超时：`请求未能及时开始，请检查网络连接后重试。`
- socket 恢复失败：`连接已断开，多次重连失败。当前回复已停止等待。`
- 后台恢复超时：`页面返回前台后未能恢复响应状态，请刷新或重新发送。`

UI 行为：

- assistant 消息显示错误，不继续转圈。
- `taskIds` 清空。
- `messageQueue` 可继续发送下一条，或者提示用户重新发送当前消息。

## 实施顺序

1. 保留当前未提交的 `messageId -> taskId` 改动，并补齐 watchdog 清理逻辑。
2. 增加 socket connection store 和 layout reconnect/resume 事件。
3. 在 Chat.svelte 增加 `recoverActiveChat`，并接入 foreground/reconnect/before-send/watchdog。
4. 给 `generateOpenAIChatCompletion` 增加 AbortController timeout。
5. 给 `saveChatHandler`、memory、location、inline image persistence 加软超时。
6. 增加 Android `onResume/onPause` 与 JS resume event。
7. 增加测试。

## 执行分支

- 基线分支：`dev`
- 实现分支：`optimize/socket-recovery-watchdog`
- 实现 worktree：`/root/projects/_wt/halowebui/20260609-socket-recovery`
- 实现 subagent：`Galileo` (`019eabcf-b522-7532-934e-ebc21b932a4a`)

## 验证计划

前端单元/集成测试：

- socket reconnect revision 变化时调用 `recoverActiveChat`。
- active task 为空且服务端消息 done 时，本地 assistant 变为 done。
- active task 为空且服务端消息仍空、超过 timeout 时，本地 assistant 写 error 并释放 `taskIds`。
- 发送前存在 stale pending task 时，会先 recover，再决定是否 queue。
- `generateOpenAIChatCompletion` timeout 会 abort fetch 并抛结构化错误。

后端单元测试：

- `stop_task("missing")` 幂等成功。
- `list_task_ids_by_chat_id(..., blocks_completion_only=True)` 过滤非阻塞任务。
- task metadata 包含创建时间和 blocks_completion。

手动验证：

1. 发送长响应后立刻把浏览器/Android WebView 挂后台 2 分钟，再回前台。
2. 观察 socket 是否重连，当前聊天是否自动恢复最终内容或继续等待真实 active task。
3. 断网发送，确认 30 秒左右 initial request timeout，不会无限转圈。
4. 模拟 socket 丢 `done` 事件，确认 watchdog 多次 recover 后写错误并释放队列。
5. 多模型并发发送，确认完成一个 response 只清理对应 task，不影响其他 sibling。

## 风险点

- 不能简单刷新整页，否则会破坏正在输入内容和队列状态；优先只 reload 当前 chat data。
- 服务端 task 完成后 task_id 会被清理，因此“task 不存在”不等于失败，必须结合数据库消息状态判断。
- Android 后台限制无法彻底绕过，前端必须以“回来后对账”为主，而不是假设后台 socket 一直活着。
- 保存超时后继续发送可能导致短时间内 DB 状态落后；需要后续补保存或在完成事件中由后端 upsert 最终消息。
