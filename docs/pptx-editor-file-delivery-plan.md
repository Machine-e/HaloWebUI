# PPTX 编辑与服务端文件发送计划

## 目标

让 `PPTX Editor` skill 真正完成以下闭环：

1. 服务端可以把生成的文件挂到当前 assistant 消息上，用户能直接看到附件。
2. PPTX 编辑完成后保存为新的 PPTX 文件，不覆盖原文件。
3. 新 PPTX 在聊天消息里提供下载和预览入口。
4. 文件发送能力做成通用能力，后续其他服务端工具也能复用。

## 当前问题判断

现有实现已经能把 PPTX 写入 `Files` 和 `Storage`，也已有 `/api/v1/files/{id}/content?attachment=true` 下载能力，但还没有稳定的“服务端生成文件 -> 当前 assistant 消息附件 -> 前端可见下载/预览”的统一契约。

已发现的关键断点：

- `backend/open_webui/utils/pptx_skill.py` 生成的文件带有 `generated: true`。
- `src/lib/components/chat/Messages/ResponseMessage.svelte` 当前会过滤 `generated === true` 的附件，这会导致 PPTX 附件不显示。
- `src/lib/utils/chat-message-errors.ts` 和 `backend/open_webui/utils/middleware.py` 的可见文件判断更偏向 image/code interpreter，普通文件附件容易不被视为可见输出。
- 聊天文件事件已有 `type: files` / `chat:message:files`，但缺少服务端主动发送文件的明确附件 schema 和持久化保障。
- 仓库已有 `src/lib/components/workspace/PptxViewer.svelte`，可复用其 JSZip 解析能力做聊天内 PPTX 预览。

## 设计原则

- 不把 PPTX 内容作为文本返回；skill 结果必须产生 `message.files` 附件。
- 不重造文件下载系统；复用 `Files`、`Storage` 和现有 `/api/v1/files/{id}/content`。
- 新增通用的服务端文件附件契约，PPTX skill 只是第一个生产者。
- 预览第一版优先复用仓库已有 `PptxViewer`，不强依赖 LibreOffice 或外部服务。
- 保留后续升级空间：未来可增加服务端转换 PDF/图片预览。

## 一、服务端发送文件接口

### 1. 定义统一附件 schema

新增通用 server file attachment 结构：

```json
{
	"type": "file",
	"id": "file-id",
	"name": "edited-presentation.pptx",
	"filename": "edited-presentation.pptx",
	"size": 123456,
	"content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
	"url": "/api/v1/files/file-id",
	"content_url": "/api/v1/files/file-id/content",
	"download_url": "/api/v1/files/file-id/content?attachment=true",
	"preview_url": "/api/v1/files/file-id/content",
	"source": "server_file",
	"producer": "pptx_editor",
	"preview": {
		"kind": "pptx",
		"strategy": "client_ooxml"
	}
}
```

注意：

- `source` 不使用 `code_interpreter`。
- PPTX skill 输出不再依赖 `generated: true` 才被识别。
- 如需标记由服务端生成，使用 `server_generated: true`，避免被现有前端过滤规则误伤。

### 2. 新增后端帮助函数

建议新增模块：

- `backend/open_webui/utils/server_files.py`

职责：

- `save_server_file(request, user, bytes, filename, content_type, producer, metadata)`  
  保存文件到 `Storage`，插入 `Files`，返回标准 attachment。
- `build_file_attachment(file_item, producer, preview)`  
  从 `FileModel` 构造聊天附件。
- `emit_server_files(event_emitter, attachments)`  
  发送 `{"type": "chat:message:files", "data": {"files": attachments}}`。

### 3. 补齐聊天消息持久化

实现位置：

- `backend/open_webui/utils/middleware.py`

改动：

- `_normalize_message_files` 接受标准 `server_file` attachment。
- `_has_visible_message_files` 把有 `id/url/content_url/download_url/name/filename` 的 `type=file` 也视为可见输出。
- tool result 中出现 `file/files/generated_files/attachments` 时，统一归一化为 `message.files`。
- 流式和非流式路径都要在 `chat:completion` 和 `upsert_response_message` 中保存 `files`。

### 4. 可选 REST 接口

如果需要显式接口，新增：

- `POST /api/v1/chats/{chat_id}/messages/{message_id}/files`

请求：

```json
{
	"files": [{ "id": "file-id", "producer": "pptx_editor" }]
}
```

作用：

- 服务端或后台任务可把已存在的 `Files` 记录挂到指定消息。
- 校验用户是否能读该文件。
- 更新 chat history 和 `ChatMessages`。
- 通过 socket 发 `chat:message:files`。

第一版可以先不暴露给前端，只作为后端能力和测试入口。

## 二、PPTX 编辑 skill 实现

### 1. 编辑输入

支持从当前聊天资源里读取上传 PPTX：

```json
{
	"source_file_id": "uploaded-pptx-file-id",
	"operations": [
		{ "type": "replace_text", "find": "旧文案", "replace": "新文案" },
		{ "type": "add_slide", "title": "新增页", "bullets": ["要点 1", "要点 2"] },
		{ "type": "append_notes", "slide": 2, "notes": "演讲备注" }
	],
	"filename": "edited.pptx"
}
```

### 2. 编辑输出

`edit_pptx` 必须返回：

```json
{
  "ok": true,
  "message": "PPTX edited and attached to the chat message.",
  "file": { "...标准 server_file attachment..." },
  "files": [{ "...标准 server_file attachment..." }]
}
```

### 3. 后端接入点

实现位置：

- `backend/open_webui/utils/pptx_skill.py`
- `backend/open_webui/utils/builtin_tools.py`
- `backend/open_webui/utils/middleware.py`

改动：

- `_save_pptx_file` 改为调用 `save_server_file` 或输出同一 schema。
- `create_pptx_edit_file` 返回 `files`，不只返回文本 JSON。
- builtin tool 调用后立即把 tool result 里的 file 归一化到 `message.files`。
- 如果模型只调用了 tool 但没有正文，assistant 消息仍应因为有 `files` 而被视为有效输出。

### 4. 安全与权限

- 只允许编辑当前用户可读的 PPTX 文件，admin 维持现有权限。
- 输出文件归属当前用户。
- 输出文件 meta 记录：
  - `source_file_id`
  - `producer: pptx_editor`
  - `server_generated: true`
  - `edit_stats`
  - `created_from_skill_id`
- 不覆盖原文件。

## 三、下载功能

复用现有接口：

- 预览/读取：`GET /api/v1/files/{id}/content`
- 下载：`GET /api/v1/files/{id}/content?attachment=true`

需要修正：

- PPTX 非 attachment 读取时不要强制 `Content-Disposition: attachment`，否则 iframe 或 fetch 预览不稳定。
- 对 PPTX 返回正确 content type：
  - `application/vnd.openxmlformats-officedocument.presentationml.presentation`

前端附件按钮：

- “下载”按钮打开 `download_url`。
- “预览”按钮打开内置预览 modal。

## 四、PPTX 预览方案

### 第一版：复用现有 PptxViewer

仓库已有：

- `src/lib/components/workspace/PptxViewer.svelte`

它基于 `jszip` 读取 `.pptx` OOXML，能展示：

- slide 列表
- slide 标题
- 文本内容
- notes
- 图片数量

计划：

1. 把 `PptxViewer` 调整为通用组件，允许在聊天文件 modal 中使用。
2. 新增 `readFileArrayBufferById(token, fileId)`：
   - `GET /api/v1/files/{id}/content`
   - 返回 `ArrayBuffer`
3. 在 `FileItemModal.svelte` 中识别 PPTX：
   - content type 是 PPTX，或文件名 `.pptx`
   - 加载 array buffer
   - 渲染 `PptxViewer`
4. 保留下载按钮。

优点：

- 不新增依赖，`jszip` 已在项目依赖里。
- 不依赖容器内 LibreOffice。
- 可快速交付聊天内预览。

限制：

- 这是结构化文本预览，不是像 PowerPoint 一样的像素级版式预览。
- 图片暂不还原到 slide 画布，只显示数量。

### 第二版：服务端转换预览

如果需要接近 PowerPoint 的视觉预览，可新增服务端转换：

- 优先方案：LibreOffice headless 转 PDF，再用浏览器 PDF iframe 预览。
- 备选方案：LibreOffice 转图片，前端显示 slide 缩略图。

需要 Docker 支持：

- 在 `Dockerfile` runtime 安装 `libreoffice` 或 `libreoffice-impress`。
- 考虑镜像体积和磁盘空间。

新增接口：

- `GET /api/v1/files/{id}/preview`
- `GET /api/v1/files/{id}/preview.pdf`

第一版不建议先做该方案，因为当前容器内没有 `libreoffice/soffice`。

## 五、前端显示改动

实现位置：

- `src/lib/components/chat/Messages/ResponseMessage.svelte`
- `src/lib/components/common/FileItem.svelte`
- `src/lib/components/common/FileItemModal.svelte`
- `src/lib/apis/files/index.ts`
- `src/lib/utils/chat-message-errors.ts`

改动：

- `visibleMessageFiles` 不再过滤所有 `generated === true`，只过滤确认为 code interpreter 内部重复项的文件。
- 普通 `type=file` 且有 `id/url/content_url/download_url/name` 时必须显示。
- `FileItem` 对 server file 使用：
  - 点击默认打开 modal 预览。
  - 提供下载按钮。
- `FileItemModal` 支持 PPTX viewer。
- `hasVisibleMessageFiles` 把 PPTX 附件视为可见输出，避免显示“空回复”错误。

## 六、测试计划

### 后端单元测试

新增/更新：

- `backend/open_webui/test/unit/test_pptx_skill.py`
- `backend/open_webui/test/unit/test_server_file_attachments.py`
- `backend/open_webui/test/unit/test_chat_message_files.py`

覆盖：

- 生成 PPTX 后返回标准 attachment。
- 编辑 PPTX 后创建新文件，原文件不变。
- tool result 中 `file/files/attachments` 可归一化为 `message.files`。
- `type=file` PPTX 被 `_has_visible_message_files` 识别为可见输出。
- 权限校验：不可编辑他人文件。

### 前端测试

新增/更新：

- `src/lib/utils/chat-message-errors.test.ts`
- `src/lib/apis/files/index.test.ts`

覆盖：

- server generated PPTX file 被视为可见附件。
- `download_url/content_url` 优先级正确。
- PPTX 类型识别正确。

### 手工验证

1. 上传一个 `.pptx`。
2. 打开聊天输入 `+`，开启 `PPTX Editor`。
3. 输入：`把第一页标题改成 XXX，并新增一页总结。`
4. assistant 回复应显示一个新的 PPTX 附件。
5. 点击下载，浏览器下载新 PPTX。
6. 点击预览，modal 展示 slide 列表和文本内容。
7. 再次下载原上传 PPTX，确认未被覆盖。

## 七、实施顺序

1. 新增 `server_files.py`，定义服务端文件保存与 attachment schema。
2. 修后端 middleware：
   - 文件归一化
   - 可见输出判定
   - tool result -> message.files 持久化
3. 调整 `pptx_skill.py` 输出标准 attachment。
4. 调整 `builtin_tools.py`，确保 `edit_pptx` 结果进入文件事件。
5. 调整前端可见性规则，让 PPTX 附件显示。
6. 把 `PptxViewer` 接入 `FileItemModal`。
7. 增加下载按钮和预览按钮。
8. 补测试。
9. 构建前端并重启 Docker 挂载版本。

### 触发与兜底策略

- 当 `PPTX Editor` 已开启、当前聊天资源包含 `.pptx`，且用户请求包含“美化 / 修改 / 编辑 / 优化 / 排版 / 返回 PPT 文件”等编辑意图时，后端会注入 `pptx_editor_trigger` 系统提示，要求模型调用 `execute_skill_entrypoint` 的 `edit_pptx`。
- `edit_pptx` 支持 `beautify` 操作，适合“美化这个 PPT”这类没有明确文字替换参数的请求。
- 如果模型仍然只回复文本、没有产生 PPTX 附件，服务端在最终保存 assistant 消息前自动执行一次 `edit_pptx` 兜底，生成新的 PPTX 附件并发送 `chat:message:files` 事件。
- 如果 assistant 消息里已经有 PPTX 附件，兜底不会重复生成。

## 八、验收标准

- 聊天中能看到 `PPTX Editor` 开关。
- 上传 PPTX 后执行编辑，assistant 消息出现新的 PPTX 附件。
- 附件可下载，文件扩展名和 content type 正确。
- 附件可预览，至少能显示 slide 文本、notes、页数。
- 刷新页面后附件仍存在。
- 原 PPTX 未被覆盖。
- 空文本但有 PPTX 附件的 assistant 消息不报“空回复”。
