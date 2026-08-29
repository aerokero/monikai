"""HTTP endpoints for MCP Hub and Tool Registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from pydantic import BaseModel

from backend.mcp.hub import get_mcp_hub
from backend.mcp.protocol import MCPServerConfig


class ToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}
    approved: bool = False


class AddServerRequest(BaseModel):
    name: str
    transport: str = "stdio"
    command: Optional[str] = None
    args: List[str] = []
    env: Dict[str, str] = {}
    auto_approve_tools: List[str] = []


class RemoveServerRequest(BaseModel):
    name: str


def register_mcp_http_routes(app):
    @app.get("/api/v1/mcp/servers")
    async def list_mcp_servers():
        hub = get_mcp_hub()
        if not hub._initialized:
            await hub.initialize()
        return {"status": "ok", "hub": hub.get_status()}

    @app.get("/api/v1/mcp/tools")
    async def list_mcp_tools(query: Optional[str] = None, top_k: int = 20):
        hub = get_mcp_hub()
        if not hub._initialized:
            await hub.initialize()

        if query:
            tools = hub.registry.select_tools(query, top_k=top_k)
        else:
            tools = hub.registry.list_all_tools()

        return {
            "status": "ok",
            "count": len(tools),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "server": t.server_name,
                    "requires_approval": t.requires_approval,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ],
        }

    @app.post("/api/v1/mcp/tools/call")
    async def call_mcp_tool(req: ToolCallRequest):
        hub = get_mcp_hub()
        if not hub._initialized:
            await hub.initialize()

        result = await hub.call_tool(req.name, req.arguments, approved=req.approved)
        return {
            "ok": not result.is_error,
            "tool": req.name,
            "content": result.content,
            "is_error": result.is_error,
            "raw": result.raw,
        }

    @app.post("/api/v1/mcp/servers/add")
    async def add_mcp_server(req: AddServerRequest):
        hub = get_mcp_hub()
        cfg = MCPServerConfig(
            name=req.name,
            transport=req.transport,
            command=req.command,
            args=req.args,
            env=req.env,
            auto_approve_tools=req.auto_approve_tools,
        )
        success = await hub.add_server(cfg)
        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to connect and add MCP server '{req.name}'")
        return {"ok": True, "server": req.name}

    @app.post("/api/v1/mcp/servers/remove")
    async def remove_mcp_server(req: RemoveServerRequest):
        hub = get_mcp_hub()
        success = await hub.remove_server(req.name)
        return {"ok": success, "server": req.name}
