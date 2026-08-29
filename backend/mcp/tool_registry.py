"""Tool Registry & Tool-RAG: Dynamic tool selection and legacy OpenClaw bridge."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .protocol import MCPTool, MCPToolResult

logger = logging.getLogger(__name__)


class ToolRAGSelector:
    """Selects the most relevant tools for a prompt using lexical scoring and category routing."""

    def __init__(self):
        # Keyword triggers mapping to tool names
        self.trigger_keywords: Dict[str, Set[str]] = {
            "filesystem": {"plik", "zapisz", "otwórz", "odczytaj", "folder", "katalog", "file", "write", "read", "dir"},
            "system_info": {"system", "ram", "cpu", "pamięć", "dysk", "procesor", "specyfikacja", "specs", "hardware"},
            "shell": {"uruchom", "polecenie", "terminal", "konsola", "bash", "exec", "run", "command"},
            "research": {"szukaj", "wyszukaj", "znajdź", "sprawdź", "artykuł", "informacje", "search", "google", "research", "web"},
            "docs": {"dokument", "notatka", "esej", "tekst", "napisz", "edytuj", "doc", "document", "draft"},
            "email": {"mail", "wiadomość", "skrzynka", "imap", "smtp", "wyślij", "inbox"},
            "calendar": {"kalendarz", "spotkanie", "wydarzenie", "termin", "przypomnij", "calendar", "event"},
        }

    def score_tool(self, tool: MCPTool, query: str) -> float:
        """Calculate relevance score between tool and query."""
        if not query:
            return 1.0

        query_lower = query.lower()
        query_words = set(re.findall(r"\w+", query_lower))

        score = 0.0

        # Exact name or description matches
        tool_name_clean = tool.name.lower().replace("_", " ")
        tool_words = set(re.findall(r"\w+", tool_name_clean))
        desc_words = set(re.findall(r"\w+", tool.description.lower()))

        # Overlap in name is heavily rewarded
        name_overlap = len(query_words.intersection(tool_words))
        score += name_overlap * 3.0

        # Overlap in description
        desc_overlap = len(query_words.intersection(desc_words))
        score += desc_overlap * 1.0

        # Keyword trigger matching
        server_key = tool.server_name.lower()
        if server_key in self.trigger_keywords:
            matched_keywords = query_words.intersection(self.trigger_keywords[server_key])
            score += len(matched_keywords) * 2.5

        return score

    def select(
        self,
        tools: List[MCPTool],
        query: str,
        top_k: int = 8,
        always_include_servers: Optional[List[str]] = None,
    ) -> List[MCPTool]:
        """Return the top-k most relevant tools for the query."""
        if len(tools) <= top_k:
            return tools

        always_servers = set(always_include_servers or ["filesystem"])
        selected: List[MCPTool] = []
        candidates: List[Tuple[float, MCPTool]] = []

        for t in tools:
            if t.server_name in always_servers:
                selected.append(t)
            else:
                score = self.score_tool(t, query)
                candidates.append((score, t))

        # Sort candidates descending by score
        candidates.sort(key=lambda x: x[0], reverse=True)

        slots_remaining = max(0, top_k - len(selected))
        for _, tool in candidates[:slots_remaining]:
            selected.append(tool)

        return selected


class ToolRegistry:
    """Central registry of all callable tools (MCP, built-ins, OpenClaw)."""

    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}
        self._tool_callers: Dict[str, Callable[[str, Dict[str, Any]], Any]] = {}
        self.selector = ToolRAGSelector()

    def register_tool(self, tool: MCPTool, caller: Callable[[str, Dict[str, Any]], Any]) -> None:
        self._tools[tool.name] = tool
        self._tool_callers[tool.name] = caller
        logger.debug(f"Registered tool '{tool.name}' from server '{tool.server_name}'")

    def unregister_server_tools(self, server_name: str) -> None:
        to_remove = [name for name, t in self._tools.items() if t.server_name == server_name]
        for name in to_remove:
            self._tools.pop(name, None)
            self._tool_callers.pop(name, None)

    def get_tool(self, name: str) -> Optional[MCPTool]:
        return self._tools.get(name)

    def list_all_tools(self) -> List[MCPTool]:
        return list(self._tools.values())

    def select_tools(self, query: str, top_k: int = 8) -> List[MCPTool]:
        return self.selector.select(list(self._tools.values()), query, top_k=top_k)

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        caller = self._tool_callers.get(name)
        if not caller:
            return MCPToolResult.text(f"Tool '{name}' not found in registry", is_error=True)

        try:
            res = caller(name, arguments)
            if hasattr(res, "__await__"):
                return await res
            return res
        except Exception as e:
            return MCPToolResult.text(f"Error calling tool '{name}': {e}", is_error=True)

    def to_openai_tool_schemas(self, tools: Optional[List[MCPTool]] = None) -> List[Dict[str, Any]]:
        """Convert MCP tools to OpenAI/OpenRouter tool format."""
        target_tools = tools if tools is not None else list(self._tools.values())
        schemas = []
        for t in target_tools:
            schemas.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            })
        return schemas
