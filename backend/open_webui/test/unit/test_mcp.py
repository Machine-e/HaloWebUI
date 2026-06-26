import asyncio
import contextlib
import json
import os
import pathlib
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

# Ensure `open_webui` is importable when running tests from repo root.
_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[3]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def test_mcp_tool_call_timeout_default_is_five_minutes():
    env = os.environ.copy()
    env.pop("MCP_TOOL_CALL_TIMEOUT", None)
    env["PYTHONPATH"] = str(_BACKEND_DIR)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from open_webui.env import MCP_TOOL_CALL_TIMEOUT; print(MCP_TOOL_CALL_TIMEOUT)",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout.strip().splitlines()[-1] == "300"


def test_mcp_streamable_http_client_json_and_sse():
    from aiohttp import web

    from open_webui.utils.mcp import MCPStreamableHttpClient

    seen_session_headers = []
    seen_custom_headers = []

    async def handler(request: web.Request):
        payload = await request.json()
        method = payload.get("method")

        # Record session header usage across requests.
        seen_session_headers.append(request.headers.get("Mcp-Session-Id"))
        seen_custom_headers.append(request.headers.get("X-Custom-Header"))

        if method == "initialize":
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "serverInfo": {"name": "TestMCP", "version": "0.0.1"},
                        "capabilities": {"tools": {}},
                    },
                },
                headers={"Mcp-Session-Id": "sess_123"},
            )

        if method == "notifications/initialized":
            # JSON-RPC notification: no response body required.
            return web.Response(status=200, headers={"Mcp-Session-Id": "sess_123"})

        if method == "tools/list":
            cursor = (payload.get("params") or {}).get("cursor")
            if not cursor:
                tools = [
                    {
                        "name": "foo/bar",
                        "description": "t1",
                        "inputSchema": {"type": "object"},
                    }
                ]
                result = {"tools": tools, "nextCursor": "c2"}
            else:
                tools = [
                    {
                        "name": "echo",
                        "description": "t2",
                        "inputSchema": {"type": "object"},
                    }
                ]
                result = {"tools": tools, "nextCursor": None}

            return web.json_response(
                {"jsonrpc": "2.0", "id": payload.get("id"), "result": result},
                headers={"Mcp-Session-Id": "sess_123"},
            )

        if method == "tools/call":
            # Return SSE to exercise the Streamable HTTP parsing branch.
            resp = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Mcp-Session-Id": "sess_123",
                },
            )
            await resp.prepare(request)

            msg = {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "content": [{"type": "text", "text": "ok"}],
                    "name": (payload.get("params") or {}).get("name"),
                    "arguments": (payload.get("params") or {}).get("arguments"),
                },
            }

            await resp.write(f"data: {json.dumps(msg)}\n\n".encode("utf-8"))
            await resp.write(b"data: [DONE]\n\n")
            await resp.write_eof()
            return resp

        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"message": "unknown method"},
            },
            status=400,
        )

    async def run():
        app = web.Application()
        app.router.add_post("/", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()

        # Determine the allocated port.
        port = site._server.sockets[0].getsockname()[1]
        url = f"http://127.0.0.1:{port}/"

        try:
            client = MCPStreamableHttpClient(
                url, request_headers={"X-Custom-Header": "present-on-all-requests"}
            )
            init = await client.initialize()
            assert init.get("serverInfo", {}).get("name") == "TestMCP"

            await client.notify_initialized()
            tools = await client.list_tools()
            assert [t["name"] for t in tools] == ["foo/bar", "echo"]

            result = await client.call_tool("echo", {"x": 1})
            assert result.get("name") == "echo"
            assert result.get("arguments") == {"x": 1}
        finally:
            await runner.cleanup()

    asyncio.run(run())

    # First request (initialize) has no session id; subsequent ones should.
    assert seen_session_headers[0] in (None, "")
    assert any(h == "sess_123" for h in seen_session_headers[1:])
    assert seen_custom_headers
    assert all(h == "present-on-all-requests" for h in seen_custom_headers)


def test_mcp_streamable_http_tool_call_uses_tool_timeout():
    from aiohttp import web

    from open_webui.utils.mcp import MCPStreamableHttpClient

    async def handler(request: web.Request):
        payload = await request.json()
        method = payload.get("method")

        if method == "initialize":
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "serverInfo": {"name": "TimeoutSplitMCP"},
                        "capabilities": {"tools": {}},
                    },
                }
            )

        if method == "notifications/initialized":
            return web.Response(status=200)

        if method == "tools/list":
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "tools": [{"name": "slow", "inputSchema": {"type": "object"}}]
                    },
                }
            )

        if method == "tools/call":
            await asyncio.sleep(0.35)
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {"content": [{"type": "text", "text": "ok"}]},
                }
            )

        return web.json_response(
            {"jsonrpc": "2.0", "id": payload.get("id"), "result": {}}
        )

    async def run():
        app = web.Application()
        app.router.add_post("/", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        url = f"http://127.0.0.1:{port}/"

        try:
            client = MCPStreamableHttpClient(url, timeout_s=0.2, tool_timeout_s=1)
            await client.initialize()
            await client.notify_initialized()
            tools = await client.list_tools()
            assert tools[0]["name"] == "slow"

            result = await client.call_tool("slow", {})
            assert result["content"][0]["text"] == "ok"
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_get_tools_exposes_mcp_tool_and_routes_call(monkeypatch):
    # Avoid touching the tool DB layer.
    import open_webui.utils.tools as tools_mod

    monkeypatch.setattr(tools_mod.Tools, "get_tool_by_id", lambda _id: None)

    called = {}

    async def fake_execute_mcp_tool(
        connection, *, name, arguments, session_token=None, **_kwargs
    ):
        called["connection"] = connection
        called["name"] = name
        called["arguments"] = arguments
        called["session_token"] = session_token
        return {"ok": True}

    monkeypatch.setattr(tools_mod, "execute_mcp_tool", fake_execute_mcp_tool)

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(
                    MCP_SERVER_CONNECTIONS=[
                        {"url": "http://mcp.local", "auth_type": "none"}
                    ],
                    TOOL_SERVER_CONNECTIONS=[],
                ),
                MCP_SERVERS=[
                    {
                        "idx": 0,
                        "url": "http://mcp.local",
                        "server_info": {"name": "TestMCP"},
                        "tools": [
                            {
                                "name": "foo/bar",
                                "description": "desc",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"a": {"type": "string"}},
                                    "required": ["a"],
                                },
                            }
                        ],
                    }
                ],
                TOOL_SERVERS=[],
            )
        ),
        state=SimpleNamespace(token=SimpleNamespace(credentials="tok_abc")),
    )
    user = SimpleNamespace(id="u1", role="admin")

    tools = tools_mod.get_tools(request, ["mcp:0"], user, extra_params={})
    assert "mcp_tool_0__foo_bar" in tools
    spec = tools["mcp_tool_0__foo_bar"]["spec"]
    assert spec["name"] == "mcp_tool_0__foo_bar"
    assert spec["parameters"]["type"] == "object"

    async def run():
        out = await tools["mcp_tool_0__foo_bar"]["callable"](a="x")
        return out

    out = asyncio.run(run())
    assert out == {"ok": True}
    assert called["name"] == "foo/bar"
    assert called["arguments"] == {"a": "x"}
    assert called["session_token"] == "tok_abc"


def test_get_tools_emits_mcp_keepalive_status_for_slow_call(monkeypatch):
    import open_webui.utils.tools as tools_mod

    monkeypatch.setattr(tools_mod.Tools, "get_tool_by_id", lambda _id: None)
    monkeypatch.setattr(tools_mod, "MCP_TOOL_CALL_TIMEOUT", 300)

    events = []
    real_sleep = asyncio.sleep
    second_keepalive_sleep = asyncio.Event()

    async def fake_sleep(delay):
        if delay == 20:
            if not any(
                event.get("data", {}).get("action") == "mcp_tool_execution"
                and event.get("data", {}).get("done") is False
                for event in events
            ):
                await real_sleep(0)
                return
            await second_keepalive_sleep.wait()
        await real_sleep(delay)

    monkeypatch.setattr(tools_mod.asyncio, "sleep", fake_sleep)

    async def fake_execute_mcp_tool(connection, *, name, arguments, **_kwargs):
        while not any(
            event.get("data", {}).get("action") == "mcp_tool_execution"
            and event.get("data", {}).get("done") is False
            for event in events
        ):
            await real_sleep(0)
        return {"ok": True}

    monkeypatch.setattr(tools_mod, "execute_mcp_tool", fake_execute_mcp_tool)

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                config=SimpleNamespace(
                    MCP_SERVER_CONNECTIONS=[
                        {"url": "http://mcp.local", "auth_type": "none"}
                    ],
                    TOOL_SERVER_CONNECTIONS=[],
                ),
                MCP_SERVERS=[
                    {
                        "idx": 0,
                        "url": "http://mcp.local",
                        "server_info": {"name": "TestMCP"},
                        "tools": [
                            {
                                "name": "slow/tool",
                                "description": "desc",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ],
                    }
                ],
                TOOL_SERVERS=[],
            )
        ),
        state=SimpleNamespace(token=SimpleNamespace(credentials="tok_abc")),
    )
    user = SimpleNamespace(id="u1", role="admin")

    async def event_emitter(event):
        events.append(event)

    async def run():
        tools = tools_mod.get_tools(request, ["mcp:0"], user, extra_params={})
        return await tools["mcp_tool_0__slow_tool"]["callable"](
            __event_emitter__=event_emitter
        )

    out = asyncio.run(run())

    assert out == {"ok": True}
    assert any(
        event["data"]["action"] == "mcp_tool_execution"
        and event["data"]["done"] is False
        and "最长等待 5 分钟" in event["data"]["description"]
        for event in events
    )
    assert events[-1]["data"] == {
        "action": "mcp_tool_execution",
        "description": "MCP 工具「slow/tool」执行结束",
        "done": True,
    }


def test_tools_route_prefers_custom_mcp_title_and_description(monkeypatch):
    from open_webui.routers import tools as tools_router

    monkeypatch.setattr(
        tools_router, "get_user_tool_server_connections", lambda _request, _user: []
    )
    monkeypatch.setattr(
        tools_router,
        "get_user_mcp_server_connections",
        lambda _request, _user: [
            {
                "transport_type": "stdio",
                "command": "uvx mcp-server-fetch",
                "name": "网页内容抓取",
                "description": "把网页正文提取成适合模型阅读的文本",
                "server_info": {"name": "mcp-fetch", "version": "1.2.3"},
                "verified_at": "2026-04-02T12:00:00Z",
                "config": {"enable": True},
            }
        ],
    )
    monkeypatch.setattr(
        tools_router.Tools, "get_tools_list_by_user_id", lambda *_args, **_kwargs: []
    )

    async def fake_get_tool_servers_data(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        tools_router, "get_tool_servers_data", fake_get_tool_servers_data
    )

    request = SimpleNamespace(
        state=SimpleNamespace(token=SimpleNamespace(credentials="tok_abc")),
        app=SimpleNamespace(state=SimpleNamespace()),
    )
    user = SimpleNamespace(id="u1", role="admin")

    async def run():
        return await tools_router.get_tools(request, user)

    tools = asyncio.run(run())
    mcp_entry = next(tool for tool in tools if tool.id == "mcp:0")

    assert mcp_entry.name == "网页内容抓取"
    assert mcp_entry.meta.description == "把网页正文提取成适合模型阅读的文本"


def test_get_mcp_server_display_metadata_falls_back_when_custom_values_missing():
    from open_webui.utils.mcp import get_mcp_server_display_metadata

    title, description = get_mcp_server_display_metadata(
        {
            "transport_type": "http",
            "url": "https://mcp.example.com/v1/mcp",
            "server_info": {"name": "mcp-fetch"},
        },
        index=0,
        default_description="MCP (HTTP) - 未验证",
        prefer_hostname_for_http=True,
    )

    assert title == "mcp-fetch"
    assert description == "MCP (HTTP) - 未验证"


def test_http_client_protocol_negotiation_retries_on_http_error():
    from aiohttp import web

    from open_webui.utils.mcp import MCPStreamableHttpClient

    seen_protocol_versions = []

    async def handler(request: web.Request):
        payload = await request.json()
        method = payload.get("method")
        protocol_version = request.headers.get("MCP-Protocol-Version")
        seen_protocol_versions.append((method, protocol_version))

        if method == "initialize":
            requested = (payload.get("params") or {}).get("protocolVersion")
            if requested == "2025-06-18":
                return web.json_response(
                    {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "error": {
                            "code": -32000,
                            "message": "Unsupported protocol version (supported versions: 2024-11-05)",
                        },
                    },
                    status=400,
                )

            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "LegacyMCP"},
                        "capabilities": {"tools": {}},
                    },
                },
                headers={"Mcp-Session-Id": "legacy_sess"},
            )

        if method == "notifications/initialized":
            return web.Response(status=200, headers={"Mcp-Session-Id": "legacy_sess"})

        if method == "tools/list":
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "tools": [
                            {
                                "name": "legacy_tool",
                                "description": "legacy",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                },
                headers={"Mcp-Session-Id": "legacy_sess"},
            )

        return web.json_response(
            {"jsonrpc": "2.0", "id": payload.get("id"), "result": {}}
        )

    async def run():
        app = web.Application()
        app.router.add_post("/", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        url = f"http://127.0.0.1:{port}/"

        try:
            client = MCPStreamableHttpClient(url)
            result = await client.initialize()
            assert result.get("serverInfo", {}).get("name") == "LegacyMCP"
            assert client.protocol_version == "2024-11-05"

            await client.notify_initialized()
            tools = await client.list_tools()
            assert tools[0]["name"] == "legacy_tool"
        finally:
            await runner.cleanup()

    asyncio.run(run())

    assert ("initialize", "2025-06-18") in seen_protocol_versions
    assert ("initialize", "2024-11-05") in seen_protocol_versions
    assert ("tools/list", "2024-11-05") in seen_protocol_versions


def test_http_client_falls_back_to_legacy_sse_transport():
    from aiohttp import web

    from open_webui.utils.mcp import MCPHttpClient

    root_post_calls = 0
    sse_connects = 0
    posted_methods = []
    outbound_events: asyncio.Queue = asyncio.Queue()

    async def sse_handler(request: web.Request):
        nonlocal sse_connects
        sse_connects += 1

        resp = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream"},
        )
        await resp.prepare(request)
        await resp.write(b"event: endpoint\ndata: /messages\n\n")

        try:
            while True:
                event = await outbound_events.get()
                if event is None:
                    break

                event_type, payload = event
                body = json.dumps(payload)
                await resp.write(
                    f"event: {event_type}\ndata: {body}\n\n".encode("utf-8")
                )
        except (ConnectionResetError, RuntimeError):
            pass
        finally:
            with contextlib.suppress(Exception):
                await resp.write_eof()

        return resp

    async def root_post_handler(_request: web.Request):
        nonlocal root_post_calls
        root_post_calls += 1
        return web.Response(status=405, text="Method Not Allowed")

    async def message_post_handler(request: web.Request):
        payload = await request.json()
        method = payload.get("method")
        posted_methods.append(method)

        if method == "initialize":
            await outbound_events.put(
                (
                    "message",
                    {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "serverInfo": {"name": "LegacySSE", "version": "0.1.0"},
                            "capabilities": {"tools": {}},
                        },
                    },
                )
            )
        elif method == "tools/list":
            await outbound_events.put(
                (
                    "message",
                    {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "result": {
                            "tools": [
                                {
                                    "name": "legacy_echo",
                                    "description": "echo via legacy sse",
                                    "inputSchema": {"type": "object"},
                                }
                            ]
                        },
                    },
                )
            )
        elif method == "tools/call":
            await asyncio.sleep(0.35)
            await outbound_events.put(
                (
                    "message",
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/message",
                        "params": {"level": "info", "data": "legacy progress"},
                    },
                )
            )
            await outbound_events.put(
                (
                    "message",
                    {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "result": {
                            "content": [{"type": "text", "text": "legacy-ok"}],
                            "name": (payload.get("params") or {}).get("name"),
                        },
                    },
                )
            )

        return web.Response(status=202)

    async def run():
        app = web.Application()
        app.router.add_get("/sse", sse_handler)
        app.router.add_post("/sse", root_post_handler)
        app.router.add_post("/messages", message_post_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        url = f"http://127.0.0.1:{port}/sse"

        client = MCPHttpClient(url, timeout_s=0.2, tool_timeout_s=1)
        try:
            init = await client.initialize()
            assert init.get("serverInfo", {}).get("name") == "LegacySSE"

            await client.notify_initialized()
            tools = await client.list_tools()
            assert tools[0]["name"] == "legacy_echo"

            notifications = []

            async def on_notification(msg):
                notifications.append(msg)

            result = await client.call_tool(
                "legacy_echo",
                {"x": 1},
                on_notification=on_notification,
            )
            assert result["content"][0]["text"] == "legacy-ok"
            assert notifications[0]["method"] == "notifications/message"
        finally:
            await outbound_events.put(None)
            await client.close()
            await runner.cleanup()

    asyncio.run(run())

    assert root_post_calls == 1
    assert sse_connects == 1
    assert posted_methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]


def test_execute_mcp_tool_uses_short_connection_timeout_and_long_tool_timeout(
    monkeypatch,
):
    from open_webui.utils import mcp as mcp_mod

    captured = {}

    class FakeMCPHttpClient:
        def __init__(
            self,
            url,
            *,
            request_headers=None,
            protocol_version=None,
            timeout_s=None,
            tool_timeout_s=None,
        ):
            captured["init"] = {
                "url": url,
                "request_headers": request_headers,
                "protocol_version": protocol_version,
                "timeout_s": timeout_s,
                "tool_timeout_s": tool_timeout_s,
            }

        async def initialize(self):
            captured["initialized"] = True
            return {}

        async def notify_initialized(self):
            captured["notified"] = True

        async def call_tool(self, *, name, arguments, on_notification=None):
            captured["call"] = {
                "name": name,
                "arguments": arguments,
                "on_notification": on_notification,
            }
            return {"ok": True}

        async def close(self):
            captured["closed"] = True

    monkeypatch.setattr(mcp_mod, "MCP_TOOL_CALL_TIMEOUT", 300)
    monkeypatch.setattr(mcp_mod, "MCPHttpClient", FakeMCPHttpClient)

    async def run():
        return await mcp_mod.execute_mcp_tool(
            {"transport_type": "http", "url": "http://mcp.local"},
            name="slow",
            arguments={"a": "x"},
        )

    assert asyncio.run(run()) == {"ok": True}
    assert (
        captured["init"]["timeout_s"] == mcp_mod.AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA
    )
    assert captured["init"]["tool_timeout_s"] == 300
    assert captured["call"]["name"] == "slow"
    assert captured["call"]["arguments"] == {"a": "x"}
    assert captured["closed"] is True


def test_execute_mcp_tool_reports_connection_timeout_separately(monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    captured = {}

    class FakeMCPHttpClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def initialize(self):
            raise asyncio.TimeoutError()

        async def notify_initialized(self):
            captured["notified"] = True

        async def call_tool(self, **_kwargs):
            captured["called"] = True
            return {}

        async def close(self):
            captured["closed"] = True

    monkeypatch.setattr(mcp_mod, "MCPHttpClient", FakeMCPHttpClient)

    async def run():
        with pytest.raises(mcp_mod.MCPConnectionTimeout, match="服务器连接超过"):
            await mcp_mod.execute_mcp_tool(
                {"transport_type": "http", "url": "http://mcp.local"},
                name="slow",
                arguments={},
            )

    asyncio.run(run())
    assert "notified" not in captured
    assert "called" not in captured
    assert captured["closed"] is True


def test_execute_mcp_tool_reports_tool_timeout_with_tool_name(monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    captured = {}

    class FakeMCPHttpClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def initialize(self):
            return {}

        async def notify_initialized(self):
            captured["notified"] = True

        async def call_tool(self, **_kwargs):
            raise asyncio.TimeoutError()

        async def close(self):
            captured["closed"] = True

    monkeypatch.setattr(mcp_mod, "MCP_TOOL_CALL_TIMEOUT", 300)
    monkeypatch.setattr(mcp_mod, "MCPHttpClient", FakeMCPHttpClient)

    async def run():
        with pytest.raises(
            mcp_mod.MCPToolCallTimeout,
            match="MCP 工具「slow」执行超过 5 分钟",
        ) as exc_info:
            await mcp_mod.execute_mcp_tool(
                {"transport_type": "http", "url": "http://mcp.local"},
                name="slow",
                arguments={},
            )
        assert exc_info.value.tool_name == "slow"

    asyncio.run(run())
    assert captured["notified"] is True
    assert captured["closed"] is True


def _write_stdio_server(tmp_path, script_name: str, body: str) -> str:
    script_path = tmp_path / script_name
    script_path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(script_path)


def test_mcp_stdio_client_lifecycle_and_call(tmp_path, monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    monkeypatch.setattr(
        mcp_mod,
        "DEFAULT_STDIO_ALLOWED_COMMANDS",
        mcp_mod.DEFAULT_STDIO_ALLOWED_COMMANDS
        | {pathlib.Path(sys.executable).name.lower()},
    )

    script_path = _write_stdio_server(
        tmp_path,
        "stdio_server.py",
        """
        import json
        import sys

        for raw in sys.stdin:
            msg = json.loads(raw)
            method = msg.get("method")
            if method == "initialize":
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "serverInfo": {"name": "stdio-test", "version": "1.0.0"},
                        "capabilities": {"tools": {}},
                    },
                }), flush=True)
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "echo",
                                "description": "Echo tool",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                }), flush=True)
            elif method == "tools/call":
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "method": "notifications/message",
                    "params": {"level": "info", "data": "calling"},
                }), flush=True)
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {"content": [{"type": "text", "text": "ok"}]},
                }), flush=True)
        """,
    )

    async def run():
        client = mcp_mod.MCPStdioClient(
            {
                "transport_type": "stdio",
                "command": sys.executable,
                "args": [script_path],
            }
        )
        try:
            await client.start()
            tools = await client.list_tools()
            assert client.server_info["name"] == "stdio-test"
            assert tools[0]["name"] == "echo"

            notifications = []

            async def on_notification(msg):
                notifications.append(msg)

            result = await client.call_tool(
                "echo", {"hello": "world"}, on_notification=on_notification
            )
            assert result["content"][0]["text"] == "ok"
            assert notifications[0]["method"] == "notifications/message"
        finally:
            await client.stop()

    asyncio.run(run())


def test_mcp_stdio_timeout_marks_client_tainted_and_manager_rebuilds(
    tmp_path, monkeypatch
):
    from open_webui.utils import mcp as mcp_mod

    monkeypatch.setattr(
        mcp_mod,
        "DEFAULT_STDIO_ALLOWED_COMMANDS",
        mcp_mod.DEFAULT_STDIO_ALLOWED_COMMANDS
        | {pathlib.Path(sys.executable).name.lower()},
    )
    monkeypatch.setattr(mcp_mod, "MCP_TOOL_CALL_TIMEOUT", 1)

    script_path = _write_stdio_server(
        tmp_path,
        "slow_stdio_server.py",
        """
        import json
        import sys
        import time

        for raw in sys.stdin:
            msg = json.loads(raw)
            method = msg.get("method")
            if method == "initialize":
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "serverInfo": {"name": "slow-stdio"},
                        "capabilities": {"tools": {}},
                    },
                }), flush=True)
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "sleep",
                                "description": "Sleep tool",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                }), flush=True)
            elif method == "tools/call":
                time.sleep(2)
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {"content": [{"type": "text", "text": "done"}]},
                }), flush=True)
        """,
    )

    async def run():
        manager = mcp_mod.MCPStdioProcessManager.instance()
        connection = {
            "transport_type": "stdio",
            "command": sys.executable,
            "args": [script_path],
        }

        try:
            client1 = await manager.get_or_start(connection, "user-1")
            with pytest.raises(
                mcp_mod.MCPToolCallTimeout,
                match="MCP 工具「sleep」执行超过 1 秒",
            ) as exc_info:
                await client1.call_tool("sleep", {})
            assert exc_info.value.tool_name == "sleep"
            assert client1.tainted is True

            client2 = await manager.get_or_start(connection, "user-1")
            assert client2 is not client1
        finally:
            await manager.stop_all()

    asyncio.run(run())


def test_get_mcp_servers_data_only_fetches_selected_indices(monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    seen = []

    async def fake_get_mcp_server_data(connection, **_kwargs):
        seen.append(connection["url"])
        return {
            "server_info": {"name": connection["url"]},
            "capabilities": {},
            "tools": [],
        }

    monkeypatch.setattr(mcp_mod, "get_mcp_server_data", fake_get_mcp_server_data)

    async def run():
        results = await mcp_mod.get_mcp_servers_data(
            [
                {"url": "http://one", "config": {"enable": True}},
                {"url": "http://two", "config": {"enable": True}},
                {"url": "http://three", "config": {"enable": True}},
            ],
            selected_indices={1},
            strict_selected=True,
        )
        assert [result["idx"] for result in results] == [1]

    asyncio.run(run())
    assert seen == ["http://two"]


def test_get_mcp_servers_data_strict_selected_rejects_invalid_index():
    from open_webui.utils import mcp as mcp_mod

    async def run():
        with pytest.raises(RuntimeError, match="所选 MCP 服务器当前不可用"):
            await mcp_mod.get_mcp_servers_data(
                [{"url": "http://one", "config": {"enable": True}}],
                selected_indices={2},
                strict_selected=True,
            )

    asyncio.run(run())


def test_build_mcp_http_request_headers_merges_custom_headers_with_auth():
    from open_webui.utils import mcp as mcp_mod

    headers = mcp_mod._build_mcp_http_request_headers(
        {
            "transport_type": "http",
            "auth_type": "bearer",
            "key": "secret-token",
            "headers": {"X-API-Key": "abc123", "X-Trace": 7},
        },
        None,
    )

    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["X-API-Key"] == "abc123"
    assert headers["X-Trace"] == "7"


def test_build_mcp_http_request_headers_custom_authorization_overrides_auto_auth():
    from open_webui.utils import mcp as mcp_mod

    headers = mcp_mod._build_mcp_http_request_headers(
        {
            "transport_type": "http",
            "auth_type": "session",
            "headers": {"Authorization": "Basic override-me-not"},
        },
        "session-token",
    )

    assert headers["Authorization"] == "Basic override-me-not"


def test_mcp_server_connection_validates_transport_fields():
    from pydantic import ValidationError

    from open_webui.routers.configs import MCPServerConnection

    with pytest.raises(ValidationError):
        MCPServerConnection(transport_type="http")

    with pytest.raises(ValidationError):
        MCPServerConnection(transport_type="stdio")

    http_conn = MCPServerConnection(transport_type="http", url="http://example.com")
    assert http_conn.transport_type == "http"
    assert http_conn.url == "http://example.com"

    stdio_conn = MCPServerConnection(
        transport_type="stdio",
        command="python",
        args=["server.py"],
        env={"TOKEN": "abc"},
    )
    assert stdio_conn.transport_type == "stdio"
    assert stdio_conn.command == "python"


def test_mcp_server_connection_normalizes_http_headers_and_drops_stdio_headers():
    from open_webui.routers.configs import MCPServerConnection

    http_conn = MCPServerConnection(
        transport_type="http",
        url="http://example.com",
        headers={
            " X-Api-Key ": "abc",
            "X-Trace": "123",
            "": "ignored",
        },
    )
    assert http_conn.headers == {"X-Api-Key": "abc", "X-Trace": "123"}

    stdio_conn = MCPServerConnection(
        transport_type="stdio",
        command="python",
        headers={"X-Api-Key": "should-be-dropped"},
    )
    assert stdio_conn.headers == {}


def test_mcp_server_connection_rejects_reserved_duplicate_and_multiline_headers():
    from pydantic import ValidationError

    from open_webui.routers.configs import MCPServerConnection

    with pytest.raises(ValidationError, match="保留头"):
        MCPServerConnection(
            transport_type="http",
            url="http://example.com",
            headers={"Content-Type": "application/json"},
        )

    with pytest.raises(ValidationError, match="重复"):
        MCPServerConnection(
            transport_type="http",
            url="http://example.com",
            headers={"X-API-Key": "a", "x-api-key": "b"},
        )

    with pytest.raises(ValidationError, match="换行符"):
        MCPServerConnection(
            transport_type="http",
            url="http://example.com",
            headers={"X-API-Key": "line1\nline2"},
        )


def test_validate_stdio_command_uses_connection_env_path(tmp_path, monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uvx_path = bin_dir / "uvx"
    uvx_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uvx_path.chmod(0o755)

    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    resolved = mcp_mod._validate_stdio_command(
        {"transport_type": "stdio", "command": "uvx", "env": {"PATH": str(bin_dir)}}
    )

    assert resolved == str(uvx_path)


def test_validate_stdio_command_falls_back_to_home_local_bin(tmp_path, monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    home_dir = tmp_path / "home"
    bin_dir = home_dir / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    uvx_path = bin_dir / "uvx"
    uvx_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uvx_path.chmod(0o755)

    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOME", str(home_dir))

    resolved = mcp_mod._validate_stdio_command(
        {"transport_type": "stdio", "command": "uvx"}
    )

    assert resolved == str(uvx_path)


def test_get_derived_stdio_runtime_requirements_detects_git_source():
    from open_webui.utils import mcp as mcp_mod

    assert mcp_mod._get_derived_stdio_runtime_requirements(
        {
            "transport_type": "stdio",
            "command": "uvx",
            "args": [
                "--native-tls",
                "--from",
                "git+https://github.com/example/server.git",
                "example-server",
            ],
        }
    ) == ["git"]

    assert (
        mcp_mod._get_derived_stdio_runtime_requirements(
            {
                "transport_type": "stdio",
                "command": "uvx",
                "args": ["mcp-server-fetch"],
            }
        )
        == []
    )


def test_validate_stdio_command_requires_git_for_uvx_git_source(monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    monkeypatch.setattr(
        mcp_mod,
        "_resolve_stdio_command",
        lambda _connection, command: (
            f"/resolved/{command}" if command == "uvx" else None
        ),
    )

    with pytest.raises(ValueError, match="Git 源安装"):
        mcp_mod._validate_stdio_command(
            {
                "transport_type": "stdio",
                "command": "uvx",
                "args": [
                    "--from",
                    "git+https://github.com/example/server.git",
                    "example-server",
                ],
            }
        )


def test_validate_stdio_command_requires_git_for_uvx_git_source_with_path(
    tmp_path, monkeypatch
):
    from open_webui.utils import mcp as mcp_mod

    uvx_path = tmp_path / "uvx"
    uvx_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uvx_path.chmod(0o755)

    monkeypatch.setattr(
        mcp_mod, "_resolve_stdio_command", lambda _connection, command: None
    )

    with pytest.raises(ValueError, match="Git 源安装"):
        mcp_mod._validate_stdio_command(
            {
                "transport_type": "stdio",
                "command": str(uvx_path),
                "args": [
                    "--from",
                    "git+https://github.com/example/server.git",
                    "example-server",
                ],
            }
        )


def test_get_mcp_runtime_capabilities_reports_preset_commands(monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    monkeypatch.setattr(
        mcp_mod,
        "_resolve_stdio_command",
        lambda _connection, command: (
            f"/resolved/{command}" if command in {"uvx", "git"} else None
        ),
    )

    capabilities = mcp_mod.get_mcp_runtime_capabilities()

    assert capabilities["commands"]["uvx"]["available"] is True
    assert capabilities["commands"]["uvx"]["message"] is None
    assert capabilities["commands"]["git"]["available"] is True
    assert capabilities["commands"]["git"]["message"] is None
    assert capabilities["commands"]["npx"]["available"] is False
    assert "Node.js" in capabilities["commands"]["npx"]["message"]


def test_get_mcp_runtime_profile_prefers_known_profiles(monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    monkeypatch.setenv("HALO_RUNTIME_PROFILE", "slim")
    assert mcp_mod.get_mcp_runtime_profile() == "slim"

    monkeypatch.setenv("HALO_RUNTIME_PROFILE", "main")
    assert mcp_mod.get_mcp_runtime_profile() == "main"

    monkeypatch.setenv("HALO_RUNTIME_PROFILE", "weird")
    assert mcp_mod.get_mcp_runtime_profile() == "custom"


def test_mcp_stdio_start_failure_includes_stderr(tmp_path, monkeypatch):
    from open_webui.utils import mcp as mcp_mod

    monkeypatch.setattr(
        mcp_mod,
        "DEFAULT_STDIO_ALLOWED_COMMANDS",
        mcp_mod.DEFAULT_STDIO_ALLOWED_COMMANDS
        | {pathlib.Path(sys.executable).name.lower()},
    )

    script_path = _write_stdio_server(
        tmp_path,
        "stderr_exit_stdio.py",
        """
        import sys

        sys.stderr.write("missing dependency\\n")
        sys.stderr.flush()
        sys.exit(1)
        """,
    )

    async def run():
        client = mcp_mod.MCPStdioClient(
            {
                "transport_type": "stdio",
                "command": sys.executable,
                "args": [script_path],
            }
        )
        with pytest.raises(RuntimeError) as exc_info:
            await client.start()

        assert "exited before initialization" in str(exc_info.value)
        assert "stderr:" in str(exc_info.value)
        assert "missing dependency" in str(exc_info.value)

    asyncio.run(run())


def test_mcp_stdio_start_failure_without_stderr_reports_initialize_exit(
    tmp_path, monkeypatch
):
    from open_webui.utils import mcp as mcp_mod

    monkeypatch.setattr(
        mcp_mod,
        "DEFAULT_STDIO_ALLOWED_COMMANDS",
        mcp_mod.DEFAULT_STDIO_ALLOWED_COMMANDS
        | {pathlib.Path(sys.executable).name.lower()},
    )

    script_path = _write_stdio_server(
        tmp_path,
        "silent_exit_stdio.py",
        """
        raise SystemExit(1)
        """,
    )

    async def run():
        client = mcp_mod.MCPStdioClient(
            {
                "transport_type": "stdio",
                "command": sys.executable,
                "args": [script_path],
            }
        )
        with pytest.raises(RuntimeError) as exc_info:
            await client.start()

        assert "exited before initialization" in str(exc_info.value)
        assert "进程提前退出，未返回 MCP initialize 响应" in str(exc_info.value)

    asyncio.run(run())


def test_mcp_servers_config_get_includes_runtime_capabilities(monkeypatch):
    from open_webui.routers import configs as configs_router

    monkeypatch.setattr(
        configs_router,
        "get_user_mcp_server_connections",
        lambda _request, _user: [
            {"transport_type": "http", "url": "http://example.com"}
        ],
    )
    monkeypatch.setattr(
        configs_router,
        "get_mcp_runtime_capabilities",
        lambda: {"commands": {"uvx": {"available": True, "message": None}}},
    )
    monkeypatch.setattr(configs_router, "get_mcp_runtime_profile", lambda: "main")

    async def run():
        return await configs_router.get_mcp_servers_config(
            SimpleNamespace(),
            SimpleNamespace(id="u1", role="admin"),
        )

    result = asyncio.run(run())

    assert result["MCP_SERVER_CONNECTIONS"][0]["url"] == "http://example.com"
    assert result["MCP_RUNTIME_CAPABILITIES"]["commands"]["uvx"]["available"] is True
    assert result["MCP_RUNTIME_PROFILE"] == "main"


def test_mcp_servers_config_post_includes_runtime_capabilities(monkeypatch):
    from open_webui.routers import configs as configs_router

    saved = {}

    monkeypatch.setattr(
        configs_router,
        "set_user_mcp_server_connections",
        lambda _user, connections: saved.setdefault("connections", connections),
    )
    monkeypatch.setattr(
        configs_router,
        "get_mcp_runtime_capabilities",
        lambda: {"commands": {"npx": {"available": False, "message": "missing"}}},
    )
    monkeypatch.setattr(configs_router, "get_mcp_runtime_profile", lambda: "slim")

    form_data = configs_router.MCPServersConfigForm(
        MCP_SERVER_CONNECTIONS=[
            configs_router.MCPServerConnection(
                transport_type="http",
                url="http://example.com",
            )
        ]
    )

    async def run():
        return await configs_router.set_mcp_servers_config(
            SimpleNamespace(),
            form_data,
            user=SimpleNamespace(id="u1", role="admin"),
        )

    result = asyncio.run(run())

    assert saved["connections"][0]["url"] == "http://example.com"
    assert result["MCP_RUNTIME_CAPABILITIES"]["commands"]["npx"]["available"] is False
    assert result["MCP_RUNTIME_PROFILE"] == "slim"


def test_mcp_servers_config_post_round_trips_headers(monkeypatch):
    from open_webui.routers import configs as configs_router

    saved = {}

    monkeypatch.setattr(
        configs_router,
        "set_user_mcp_server_connections",
        lambda _user, connections: saved.setdefault("connections", connections),
    )
    monkeypatch.setattr(
        configs_router, "get_mcp_runtime_capabilities", lambda: {"commands": {}}
    )
    monkeypatch.setattr(configs_router, "get_mcp_runtime_profile", lambda: "custom")

    form_data = configs_router.MCPServersConfigForm(
        MCP_SERVER_CONNECTIONS=[
            configs_router.MCPServerConnection(
                transport_type="http",
                url="http://example.com",
                auth_type="none",
                headers={"X-API-Key": "abc123"},
            )
        ]
    )

    async def run():
        return await configs_router.set_mcp_servers_config(
            SimpleNamespace(),
            form_data,
            user=SimpleNamespace(id="u1", role="admin"),
        )

    result = asyncio.run(run())

    assert saved["connections"][0]["headers"] == {"X-API-Key": "abc123"}
    assert result["MCP_SERVER_CONNECTIONS"][0]["headers"] == {"X-API-Key": "abc123"}


def test_verify_mcp_server_connection_passes_headers_and_session_token(monkeypatch):
    from open_webui.routers import configs as configs_router

    captured = {}

    async def fake_get_mcp_server_data(connection, **kwargs):
        captured["connection"] = connection
        captured["kwargs"] = kwargs
        return {
            "server_info": {"name": "verified"},
            "tools": [
                {
                    "name": "echo",
                    "description": "Echo",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                    },
                }
            ],
        }

    monkeypatch.setattr(configs_router, "get_mcp_server_data", fake_get_mcp_server_data)

    request = SimpleNamespace(
        state=SimpleNamespace(token=SimpleNamespace(credentials="session-token"))
    )
    form_data = configs_router.MCPServerConnection(
        transport_type="http",
        url="http://example.com",
        auth_type="session",
        headers={"X-API-Key": "abc123"},
    )

    async def run():
        return await configs_router.verify_mcp_server_connection(
            request,
            form_data,
            user=SimpleNamespace(role="admin"),
        )

    result = asyncio.run(run())

    assert captured["connection"]["headers"] == {"X-API-Key": "abc123"}
    assert captured["kwargs"]["session_token"] == "session-token"
    assert result["tool_count"] == 1
    assert result["tools"] == [
        {
            "name": "echo",
            "description": "Echo",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
        }
    ]


def test_get_mcp_servers_cached_data_returns_selected_verified_snapshots():
    from open_webui.utils import mcp as mcp_mod

    results = mcp_mod.get_mcp_servers_cached_data(
        [
            {
                "transport_type": "http",
                "url": "http://one",
                "config": {"enable": True},
                "server_info": {"name": "server-one"},
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo",
                        "inputSchema": {"type": "object"},
                    }
                ],
            },
            {
                "transport_type": "http",
                "url": "http://two",
                "config": {"enable": True},
                "tools": [],
            },
        ],
        selected_indices={0},
        strict_selected=True,
    )

    assert results == [
        {
            "idx": 0,
            "transport_type": "http",
            "url": "http://one",
            "command": "",
            "server_info": {"name": "server-one"},
            "capabilities": {},
            "tools": [
                {
                    "name": "echo",
                    "description": "Echo",
                    "inputSchema": {"type": "object"},
                }
            ],
        }
    ]
