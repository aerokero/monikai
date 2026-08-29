"""Central MCP Hub managing server lifecycles, configuration, and execution."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .builtin_servers import (
    create_filesystem_server,
    create_shell_server,
    create_system_info_server,
)
from .client import InProcessMCPClient, MCPClient, StdioMCPClient
from .protocol import MCPServerConfig, MCPTool, MCPToolResult
from .tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class MCPHub:
    """Master hub managing all MCP servers, tool discovery, and execution."""

    def __init__(self, data_dir: Optional[Path] = None, workspace_root: Optional[Path] = None):
        self.data_dir = data_dir or Path("data")
        self.workspace_root = workspace_root or Path.cwd()
        self.config_path = self.data_dir / "mcp_servers.json"
        self.clients: Dict[str, MCPClient] = {}
        self.registry = ToolRegistry()
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        # 1. Register Built-in Servers
        fs_server = create_filesystem_server(self.workspace_root)
        await self._attach_client("filesystem", fs_server)

        sys_server = create_system_info_server()
        await self._attach_client("system_info", sys_server)

        shell_server = create_shell_server()
        await self._attach_client("shell", shell_server)

        # 2. Load and attach configured external servers
        configs = self._load_configs()
        for cfg in configs:
            if not cfg.enabled or cfg.name in self.clients:
                continue
            if cfg.transport == "stdio":
                client = StdioMCPClient(cfg)
                await self._attach_client(cfg.name, client)

        self._initialized = True
        logger.info(f"MCP Hub initialized with {len(self.clients)} servers and {len(self.registry.list_all_tools())} tools")

    async def _attach_client(self, name: str, client: MCPClient) -> bool:
        success = await client.connect()
        if success:
            self.clients[name] = client
            tools = await client.list_tools()
            for tool in tools:
                # Bind caller lambda to client
                self.registry.register_tool(
                    tool,
                    lambda t_name, args, cl=client: cl.call_tool(t_name, args),
                )
            return True
        return False

    def _load_configs(self) -> List[MCPServerConfig]:
        if not self.config_path.exists():
            return []
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
            servers_raw = raw.get("mcpServers", {})
            configs = []
            for name, item in servers_raw.items():
                configs.append(
                    MCPServerConfig(
                        name=name,
                        transport=item.get("transport", "stdio"),
                        command=item.get("command"),
                        args=item.get("args", []),
                        env=item.get("env", {}),
                        url=item.get("url"),
                        enabled=item.get("enabled", True),
                        auto_approve_tools=item.get("auto_approve_tools", []),
                    )
                )
            return configs
        except Exception as e:
            logger.error(f"Failed to read MCP config from {self.config_path}: {e}")
            return []

    def _save_configs(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        servers_data = {}
        for name, client in self.clients.items():
            if client.config.transport != "builtin":
                servers_data[name] = {
                    "transport": client.config.transport,
                    "command": client.config.command,
                    "args": client.config.args,
                    "env": client.config.env,
                    "url": client.config.url,
                    "enabled": client.config.enabled,
                    "auto_approve_tools": client.config.auto_approve_tools,
                }
        self.config_path.write_text(json.dumps({"mcpServers": servers_data}, indent=2), encoding="utf-8")

    async def add_server(self, config: MCPServerConfig) -> bool:
        if config.name in self.clients:
            await self.remove_server(config.name)

        if config.transport == "stdio":
            client = StdioMCPClient(config)
            ok = await self._attach_client(config.name, client)
            if ok:
                self._save_configs()
            return ok
        return False

    async def remove_server(self, name: str) -> bool:
        client = self.clients.pop(name, None)
        if client:
            await client.disconnect()
            self.registry.unregister_server_tools(name)
            self._save_configs()
            return True
        return False

    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        approved: bool = False,
    ) -> MCPToolResult:
        tool = self.registry.get_tool(name)
        if not tool:
            return MCPToolResult.text(f"Tool '{name}' not found", is_error=True)

        if tool.requires_approval and not approved:
            return MCPToolResult.text(
                f"Tool '{name}' requires user confirmation before execution.",
                is_error=True,
                raw={"requires_approval": True, "tool": name, "arguments": arguments},
            )

        return await self.registry.call_tool(name, arguments)

    def get_status(self) -> Dict[str, Any]:
        servers_info = {}
        for name, client in self.clients.items():
            servers_info[name] = {
                "name": name,
                "transport": client.config.transport,
                "connected": client.is_connected,
                "tool_count": len(client.tools),
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "requires_approval": t.requires_approval,
                    }
                    for t in client.tools.values()
                ],
            }
        return {
            "server_count": len(self.clients),
            "total_tools": len(self.registry.list_all_tools()),
            "servers": servers_info,
        }

    async def shutdown(self) -> None:
        for client in self.clients.values():
            await client.disconnect()
        self.clients.clear()


# Global singleton instance
_GLOBAL_MCP_HUB: Optional[MCPHub] = None


def get_mcp_hub(data_dir: Optional[Path] = None, workspace_root: Optional[Path] = None) -> MCPHub:
    global _GLOBAL_MCP_HUB
    if _GLOBAL_MCP_HUB is None:
        _GLOBAL_MCP_HUB = MCPHub(data_dir=data_dir, workspace_root=workspace_root)
    return _GLOBAL_MCP_HUB
