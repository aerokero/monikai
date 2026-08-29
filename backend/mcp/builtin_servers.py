import asyncio
import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psutil
except ImportError:
    psutil = None

from .client import InProcessMCPClient
from .protocol import MCPServerConfig, MCPTool, MCPToolResult


def create_filesystem_server(workspace_root: Optional[Path] = None) -> InProcessMCPClient:
    """Create built-in filesystem MCP server."""
    root = (workspace_root or Path.cwd()).resolve()

    def _resolve_safe_path(rel_or_abs: str) -> Path:
        target = Path(rel_or_abs)
        if not target.is_absolute():
            target = (root / target).resolve()
        else:
            target = target.resolve()
        return target

    async def read_file(path: str) -> MCPToolResult:
        try:
            p = _resolve_safe_path(path)
            if not p.exists() or not p.is_file():
                return MCPToolResult.text(f"File not found: {path}", is_error=True)
            content = p.read_text(encoding="utf-8", errors="replace")
            return MCPToolResult.text(content)
        except Exception as e:
            return MCPToolResult.text(f"Error reading file: {e}", is_error=True)

    async def write_file(path: str, content: str) -> MCPToolResult:
        try:
            p = _resolve_safe_path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return MCPToolResult.text(f"Successfully wrote {len(content)} characters to {p.name}")
        except Exception as e:
            return MCPToolResult.text(f"Error writing file: {e}", is_error=True)

    async def list_directory(path: str = ".") -> MCPToolResult:
        try:
            p = _resolve_safe_path(path)
            if not p.exists() or not p.is_dir():
                return MCPToolResult.text(f"Directory not found: {path}", is_error=True)
            entries = []
            for item in sorted(p.iterdir()):
                entries.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size_bytes": item.stat().st_size if item.is_file() else None,
                })
            return MCPToolResult.json(entries)
        except Exception as e:
            return MCPToolResult.text(f"Error listing directory: {e}", is_error=True)

    config = MCPServerConfig(
        name="filesystem",
        transport="builtin",
        enabled=True,
        auto_approve_tools=["read_file", "list_directory"],
    )

    handlers = {
        "read_file": read_file,
        "write_file": write_file,
        "list_directory": list_directory,
    }

    client = InProcessMCPClient(config, handlers)
    client.register_inprocess_tool(
        MCPTool(
            name="read_file",
            description="Odczytuje zawartość pliku tekstowego z dysku",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Ścieżka do pliku"}},
                "required": ["path"],
            },
            server_name="filesystem",
            requires_approval=False,
        ),
        read_file,
    )
    client.register_inprocess_tool(
        MCPTool(
            name="write_file",
            description="Zapisuje podaną treść do pliku na dysku",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ścieżka do pliku docelowego"},
                    "content": {"type": "string", "description": "Treść do zapisania"},
                },
                "required": ["path", "content"],
            },
            server_name="filesystem",
            requires_approval=True,
        ),
        write_file,
    )
    client.register_inprocess_tool(
        MCPTool(
            name="list_directory",
            description="Listuje pliki i foldery w podanym katalogu",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Ścieżka do folderu", "default": "."}},
            },
            server_name="filesystem",
            requires_approval=False,
        ),
        list_directory,
    )
    return client


def create_system_info_server() -> InProcessMCPClient:
    """Create built-in system information MCP server."""

    async def get_system_specs() -> MCPToolResult:
        try:
            specs: Dict[str, Any] = {
                "os": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python_version": platform.python_version(),
                "cpu_count": os.cpu_count(),
            }
            try:
                disk = shutil.disk_usage("/")
                specs["disk_total_gb"] = round(disk.total / (1024 ** 3), 2)
                specs["disk_free_gb"] = round(disk.free / (1024 ** 3), 2)
            except Exception:
                pass

            if psutil is not None:
                try:
                    mem = psutil.virtual_memory()
                    specs["memory_total_gb"] = round(mem.total / (1024 ** 3), 2)
                    specs["memory_available_gb"] = round(mem.available / (1024 ** 3), 2)
                    specs["memory_percent"] = mem.percent
                    specs["cpu_percent"] = psutil.cpu_percent(interval=0.1)
                except Exception:
                    pass

            return MCPToolResult.json(specs)
        except Exception as e:
            return MCPToolResult.text(f"Error fetching system specs: {e}", is_error=True)

    config = MCPServerConfig(
        name="system_info",
        transport="builtin",
        enabled=True,
        auto_approve_tools=["get_system_specs"],
    )

    handlers = {"get_system_specs": get_system_specs}
    client = InProcessMCPClient(config, handlers)
    client.register_inprocess_tool(
        MCPTool(
            name="get_system_specs",
            description="Zwraca informacje o systemie operacyjnym, CPU, RAM i dysku",
            input_schema={"type": "object", "properties": {}},
            server_name="system_info",
            requires_approval=False,
        ),
        get_system_specs,
    )
    return client


def create_shell_server() -> InProcessMCPClient:
    """Create built-in shell execution MCP server."""

    async def run_command(command: str, timeout_s: float = 30.0) -> MCPToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            out_str = stdout.decode("utf-8", errors="replace")
            err_str = stderr.decode("utf-8", errors="replace")
            is_err = proc.returncode != 0
            res_text = f"Exit code: {proc.returncode}\nStdout:\n{out_str}"
            if err_str:
                res_text += f"\nStderr:\n{err_str}"
            return MCPToolResult.text(res_text, is_error=is_err)
        except asyncio.TimeoutError:
            return MCPToolResult.text(f"Command timed out after {timeout_s} seconds", is_error=True)
        except Exception as e:
            return MCPToolResult.text(f"Error executing command: {e}", is_error=True)

    config = MCPServerConfig(
        name="shell",
        transport="builtin",
        enabled=True,
        auto_approve_tools=[],
    )

    handlers = {"run_command": run_command}
    client = InProcessMCPClient(config, handlers)
    client.register_inprocess_tool(
        MCPTool(
            name="run_command",
            description="Wykonuje polecenie powłoki shell w systemie",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Polecenie do wykonania w bashu"},
                    "timeout_s": {"type": "number", "description": "Limit czasu w sekundach", "default": 30.0},
                },
                "required": ["command"],
            },
            server_name="shell",
            requires_approval=True,
        ),
        run_command,
    )
    return client
