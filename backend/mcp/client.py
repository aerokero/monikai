"""MCP Client implementations supporting stdio, HTTP/SSE, and in-process execution."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import shutil
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

import httpx

from .protocol import MCPResource, MCPServerConfig, MCPTool, MCPToolResult

logger = logging.getLogger(__name__)


class MCPClient(ABC):
    """Abstract client for talking to a single MCP Server."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
        self.is_connected: bool = False

    @abstractmethod
    async def connect(self) -> bool:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def list_tools(self) -> List[MCPTool]:
        pass

    @abstractmethod
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        pass

    @abstractmethod
    async def list_resources(self) -> List[MCPResource]:
        pass


class StdioMCPClient(MCPClient):
    """MCP Client using JSON-RPC 2.0 over subprocess stdin/stdout."""

    def __init__(self, config: MCPServerConfig):
        super().__init__(config)
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id: int = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        if not self.config.command:
            logger.error(f"StdioMCPClient [{self.config.name}]: No command specified")
            return False

        cmd_path = shutil.which(self.config.command) or self.config.command
        env = {**os.environ, **self.config.env}

        try:
            self._process = await asyncio.create_subprocess_exec(
                cmd_path,
                *self.config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._reader_task = asyncio.create_task(self._listen_stdout())
            
            # Send initialize handshake
            init_res = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}},
                    "clientInfo": {"name": "MonikAI-Odysseus", "version": "2.0"},
                },
                timeout=10.0,
            )
            if init_res is not None:
                await self._send_notification("notifications/initialized", {})
                self.is_connected = True
                await self.list_tools()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to start MCP server {self.config.name}: {e}")
            await self.disconnect()
            return False

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        if not self._process or self._process.returncode is not None:
            raise RuntimeError(f"MCP server {self.config.name} process is not running")

        self._request_id += 1
        req_id = self._request_id
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        fut = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = fut

        msg_bytes = (json.dumps(payload) + "\n").encode("utf-8")
        if self._process.stdin:
            self._process.stdin.write(msg_bytes)
            await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending_requests.pop(req_id, None)

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        if not self._process or not self._process.stdin:
            return
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        self._process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self._process.stdin.drain()

    async def _listen_stdout(self) -> None:
        if not self._process or not self._process.stdout:
            return
        while True:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                except Exception:
                    continue

                if "id" in data and data["id"] in self._pending_requests:
                    fut = self._pending_requests[data["id"]]
                    if not fut.done():
                        if "error" in data:
                            fut.set_exception(RuntimeError(data["error"].get("message", "MCP error")))
                        else:
                            fut.set_result(data.get("result"))
            except Exception as e:
                logger.warning(f"Error reading from MCP server {self.config.name}: {e}")
                break

    async def disconnect(self) -> None:
        self.is_connected = False
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    async def list_tools(self) -> List[MCPTool]:
        try:
            res = await self._send_request("tools/list", {})
            raw_tools = (res or {}).get("tools", [])
            self.tools.clear()
            for item in raw_tools:
                name = item.get("name", "")
                tool = MCPTool(
                    name=name,
                    description=item.get("description", ""),
                    input_schema=item.get("inputSchema", {}),
                    server_name=self.config.name,
                    requires_approval=name not in self.config.auto_approve_tools,
                )
                self.tools[name] = tool
            return list(self.tools.values())
        except Exception as e:
            logger.error(f"Failed to list tools for {self.config.name}: {e}")
            return []

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        try:
            res = await self._send_request("tools/call", {"name": name, "arguments": arguments})
            content = (res or {}).get("content", [])
            is_error = bool((res or {}).get("isError", False))
            return MCPToolResult(content=content, is_error=is_error, raw=res)
        except Exception as e:
            return MCPToolResult.text(f"Error calling tool {name}: {e}", is_error=True)

    async def list_resources(self) -> List[MCPResource]:
        try:
            res = await self._send_request("resources/list", {})
            raw_resources = (res or {}).get("resources", [])
            self.resources.clear()
            for item in raw_resources:
                res_obj = MCPResource(
                    uri=item.get("uri", ""),
                    name=item.get("name", ""),
                    description=item.get("description"),
                    mime_type=item.get("mimeType"),
                    server_name=self.config.name,
                )
                self.resources[res_obj.uri] = res_obj
            return list(self.resources.values())
        except Exception as e:
            logger.warning(f"Failed to list resources for {self.config.name}: {e}")
            return []


class InProcessMCPClient(MCPClient):
    """In-memory MCP Client executing python functions directly."""

    def __init__(self, config: MCPServerConfig, tool_handlers: Dict[str, Callable]):
        super().__init__(config)
        self._handlers = tool_handlers

    async def connect(self) -> bool:
        self.is_connected = True
        return True

    async def disconnect(self) -> None:
        self.is_connected = False

    def register_inprocess_tool(self, tool: MCPTool, handler: Callable) -> None:
        self.tools[tool.name] = tool
        self._handlers[tool.name] = handler

    async def list_tools(self) -> List[MCPTool]:
        return list(self.tools.values())

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        handler = self._handlers.get(name)
        if not handler:
            return MCPToolResult.text(f"Tool '{name}' not found in in-process server", is_error=True)
        try:
            if inspect.iscoroutinefunction(handler):
                result = await handler(**arguments)
            else:
                result = handler(**arguments)

            if isinstance(result, MCPToolResult):
                return result
            elif isinstance(result, dict) or isinstance(result, list):
                return MCPToolResult.json(result)
            else:
                return MCPToolResult.text(str(result))
        except Exception as e:
            return MCPToolResult.text(f"Execution error in tool '{name}': {e}", is_error=True)

    async def list_resources(self) -> List[MCPResource]:
        return list(self.resources.values())
