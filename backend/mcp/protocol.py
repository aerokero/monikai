"""Model Context Protocol (MCP) data models and JSON-RPC primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str = "builtin"
    requires_approval: bool = False


@dataclass
class MCPResource:
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None
    server_name: str = "builtin"


@dataclass
class MCPToolResult:
    content: List[Dict[str, Any]]
    is_error: bool = False
    raw: Optional[Any] = None

    @classmethod
    def text(cls, text: str, is_error: bool = False, raw: Optional[Any] = None) -> MCPToolResult:
        return cls(content=[{"type": "text", "text": text}], is_error=is_error, raw=raw)

    @classmethod
    def json(cls, data: Any, is_error: bool = False, raw: Optional[Any] = None) -> MCPToolResult:
        import json
        return cls(
            content=[{"type": "text", "text": json.dumps(data, indent=2, ensure_ascii=False)}],
            is_error=is_error,
            raw=raw if raw is not None else data,
        )


@dataclass
class MCPServerConfig:
    name: str
    transport: str  # "stdio", "sse", "builtin"
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    enabled: bool = True
    auto_approve_tools: List[str] = field(default_factory=list)
