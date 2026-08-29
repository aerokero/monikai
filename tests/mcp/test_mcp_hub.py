import pytest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.mcp.protocol import MCPServerConfig, MCPTool, MCPToolResult
from backend.mcp.client import InProcessMCPClient
from backend.mcp.tool_registry import ToolRAGSelector, ToolRegistry
from backend.mcp.hub import MCPHub
from backend.core.routers.mcp_http_router import register_mcp_http_routes


@pytest.mark.asyncio
async def test_tool_rag_selector():
    selector = ToolRAGSelector()
    
    t_file = MCPTool(name="read_file", description="Odczytuje zawartość pliku", input_schema={}, server_name="filesystem")
    t_sys = MCPTool(name="get_system_specs", description="Sprawdza RAM i procesor", input_schema={}, server_name="system_info")
    t_shell = MCPTool(name="run_command", description="Wykonuje polecenie shell", input_schema={}, server_name="shell")
    
    tools = [t_file, t_sys, t_shell]
    
    # Query about system specs
    selected = selector.select(tools, query="ile mam wolnego ramu i jaki procesor?", top_k=2)
    names = [t.name for t in selected]
    assert "get_system_specs" in names


@pytest.mark.asyncio
async def test_mcp_hub_builtin_tools(tmp_path: Path):
    hub = MCPHub(data_dir=tmp_path, workspace_root=tmp_path)
    await hub.initialize()
    
    status = hub.get_status()
    assert status["server_count"] >= 3
    assert "filesystem" in status["servers"]
    assert "system_info" in status["servers"]
    assert "shell" in status["servers"]

    # Test tool execution: system info
    res = await hub.call_tool("get_system_specs", {})
    assert not res.is_error
    assert len(res.content) > 0
    assert "os" in res.content[0]["text"].lower() or "memory" in res.content[0]["text"].lower()

    # Test tool execution with approval gate: write_file requires approval
    res_unapproved = await hub.call_tool("write_file", {"path": "test.txt", "content": "hello"}, approved=False)
    assert res_unapproved.is_error
    assert res_unapproved.raw.get("requires_approval") is True

    # Test approved tool execution
    res_approved = await hub.call_tool("write_file", {"path": "test.txt", "content": "hello"}, approved=True)
    assert not res_approved.is_error
    assert (tmp_path / "test.txt").read_text() == "hello"

    # Test read_file
    res_read = await hub.call_tool("read_file", {"path": "test.txt"}, approved=False)
    assert not res_read.is_error
    assert res_read.content[0]["text"] == "hello"

    await hub.shutdown()


def test_mcp_http_endpoints():
    app = FastAPI()
    register_mcp_http_routes(app)
    client = TestClient(app)

    # List servers
    res = client.get("/api/v1/mcp/servers")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "hub" in data

    # List tools
    tools_res = client.get("/api/v1/mcp/tools")
    assert tools_res.status_code == 200
    tools_data = tools_res.json()
    assert tools_data["status"] == "ok"
    assert tools_data["count"] > 0

    # Call tool via HTTP
    call_res = client.post(
        "/api/v1/mcp/tools/call",
        json={"name": "get_system_specs", "arguments": {}, "approved": False},
    )
    assert call_res.status_code == 200
    call_data = call_res.json()
    assert call_data["ok"] is True
