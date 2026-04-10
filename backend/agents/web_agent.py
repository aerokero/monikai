import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlparse

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()


def _resolve_ollama_model(default_model: str = "qwen3:8b") -> str:
    explicit = str(os.getenv("WEB_AGENT_OLLAMA_MODEL", "")).strip()
    if explicit:
        return explicit
    legacy = str(os.getenv("WEB_AGENT_MODEL", "")).strip()
    if legacy and "gemini" not in legacy.lower():
        return legacy
    return default_model


SCREEN_WIDTH = int(os.getenv("WEB_AGENT_SCREEN_WIDTH", "1440"))
SCREEN_HEIGHT = int(os.getenv("WEB_AGENT_SCREEN_HEIGHT", "900"))
MODEL_ID = _resolve_ollama_model()
PLANNER_MODEL_ID = str(os.getenv("WEB_AGENT_OLLAMA_PLANNER_MODEL", "")).strip() or MODEL_ID
MAX_TURNS = int(os.getenv("WEB_AGENT_MAX_TURNS", "28"))
DEFAULT_START_URL = os.getenv("WEB_AGENT_START_URL", "https://www.google.com")
OLLAMA_BASE_URL = str(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
OLLAMA_TIMEOUT_SEC = int(os.getenv("WEB_AGENT_OLLAMA_TIMEOUT_SEC", "120"))
OLLAMA_KEEP_ALIVE = str(os.getenv("WEB_AGENT_OLLAMA_KEEP_ALIVE", "15m")).strip()
OLLAMA_TEMPERATURE_RAW = str(os.getenv("WEB_AGENT_OLLAMA_TEMPERATURE", "0.2")).strip()
OLLAMA_THINK = str(os.getenv("WEB_AGENT_OLLAMA_THINK", "0")).strip().lower() in {"1", "true", "yes", "on"}
OLLAMA_AUTO_START = str(os.getenv("WEB_AGENT_OLLAMA_AUTO_START", "1")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
OLLAMA_AUTO_PULL = str(os.getenv("WEB_AGENT_OLLAMA_AUTO_PULL", "1")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
OLLAMA_STARTUP_TIMEOUT_SEC = int(os.getenv("WEB_AGENT_OLLAMA_STARTUP_TIMEOUT_SEC", "25"))
OLLAMA_PULL_TIMEOUT_SEC = int(os.getenv("WEB_AGENT_OLLAMA_PULL_TIMEOUT_SEC", "1800"))
WEB_AGENT_REQUIRE_MANUAL_AUTH = str(os.getenv("WEB_AGENT_REQUIRE_MANUAL_AUTH", "1")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WEB_AGENT_CONFIRM_DESTRUCTIVE_ACTIONS = str(
    os.getenv("WEB_AGENT_CONFIRM_DESTRUCTIVE_ACTIONS", "1")
).strip().lower() in {"1", "true", "yes", "on"}
WEB_AGENT_CONFIRM_SENSITIVE_ACTIONS = str(
    os.getenv("WEB_AGENT_CONFIRM_SENSITIVE_ACTIONS", "1")
).strip().lower() in {"1", "true", "yes", "on"}
WEB_AGENT_CONFIRM_HIGH_RISK_DOMAIN_MUTATION = str(
    os.getenv("WEB_AGENT_CONFIRM_HIGH_RISK_DOMAIN_MUTATION", "0")
).strip().lower() in {"1", "true", "yes", "on"}
WEB_AGENT_CONFIRM_HIGH_RISK_NAVIGATION = str(
    os.getenv("WEB_AGENT_CONFIRM_HIGH_RISK_NAVIGATION", "0")
).strip().lower() in {"1", "true", "yes", "on"}
WEB_AGENT_CONFIRMATION_CACHE_TTL_SEC = max(
    0, int(os.getenv("WEB_AGENT_CONFIRMATION_CACHE_TTL_SEC", "90"))
)
WEB_AGENT_BROWSER_MODE = str(os.getenv("WEB_AGENT_BROWSER_MODE", "managed")).strip().lower()
WEB_AGENT_CDP_URL = str(os.getenv("WEB_AGENT_CDP_URL", "http://127.0.0.1:9222")).strip()
WEB_AGENT_CDP_REUSE_PAGE = str(os.getenv("WEB_AGENT_CDP_REUSE_PAGE", "0")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

SENSITIVE_ACTION_KEYWORDS = {
    "buy",
    "purchase",
    "checkout",
    "payment",
    "pay",
    "transfer",
    "wire",
    "delete account",
    "close account",
    "confirm order",
    "place order",
}
AUTH_FLOW_HINT_KEYWORDS = {
    "login",
    "log in",
    "sign in",
    "signin",
    "password",
    "passcode",
    "otp",
    "2fa",
    "verification",
    "verify",
    "identifier",
    "username",
    "accounts.google.com",
}
DESTRUCTIVE_ACTION_KEYWORDS = {
    "delete",
    "remove",
    "trash",
    "archive",
    "unsubscribe",
    "block",
    "report",
    "send",
    "submit",
    "confirm",
    "purchase",
    "checkout",
    "payment",
    "transfer",
    "wire",
    "close account",
}
HIGH_RISK_DOMAIN_KEYWORDS = {
    "mail.",
    "gmail.",
    "outlook.",
    "accounts.",
    "bank",
    "wallet",
    "paypal.",
    "stripe.",
    "coinbase.",
    "wise.",
    "revolut.",
    "admin.",
    "console.",
}


AGENT_FUNCTIONS: List[Dict[str, Any]] = [
    {
        "name": "navigate",
        "description": "Open URL in current tab.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Full URL or domain."}},
            "required": ["url"],
        },
    },
    {
        "name": "go_back",
        "description": "Go to previous page in browser history.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "go_forward",
        "description": "Go to next page in browser history.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "search",
        "description": "Perform Google search for query.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Query text."}},
            "required": ["query"],
        },
    },
    {
        "name": "wait_5_seconds",
        "description": "Wait for dynamic page content.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_page_snapshot",
        "description": "Return URL, title and visible text excerpt from current page.",
        "parameters": {
            "type": "object",
            "properties": {
                "max_chars": {"type": "integer", "description": "Max chars in text excerpt (default 2000)."}
            },
        },
    },
    {
        "name": "extract_links",
        "description": "Extract visible links from current page.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max links (default 20)."}},
        },
    },
    {
        "name": "click_selector",
        "description": "Click element matched by CSS selector.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector to click."},
                "index": {"type": "integer", "description": "0-based element index (default 0)."},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "type_selector",
        "description": "Type text into element matched by CSS selector.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector for input/textarea."},
                "text": {"type": "string", "description": "Text to type."},
                "press_enter": {"type": "boolean", "description": "Press Enter after typing."},
                "clear_before_typing": {"type": "boolean", "description": "Clear existing input first."},
            },
            "required": ["selector", "text"],
        },
    },
    {
        "name": "wait_for_selector",
        "description": "Wait until selector appears on page.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector to wait for."},
                "timeout_ms": {"type": "integer", "description": "Timeout in ms (default 10000)."},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "press_key",
        "description": "Press keyboard key or shortcut combination.",
        "parameters": {
            "type": "object",
            "properties": {"keys": {"type": "string"}},
            "required": ["keys"],
        },
    },
    {
        "name": "scroll_document",
        "description": "Scroll current page.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "description": "down|up|left|right"},
                "magnitude": {"type": "integer"},
            },
        },
    },
    {
        "name": "finish_task",
        "description": "Call when task is done with concise final summary.",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string", "description": "Final answer for user."}},
            "required": ["summary"],
        },
    },
]


class WebAgent:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.model_id = MODEL_ID
        self.planner_model_id = PLANNER_MODEL_ID
        self.max_turns = MAX_TURNS
        # Desktop app default: run headed so user can complete manual login/2FA in real browser window.
        self.headless = self._truthy(os.getenv("WEB_AGENT_HEADLESS", "0"))
        self.enable_sensitive_approvals = self._truthy(os.getenv("WEB_AGENT_REQUIRE_ACTION_CONFIRM", "1"))
        self._finish_requested = False
        self._finish_summary = ""
        self.ollama_base_url = OLLAMA_BASE_URL
        self.ollama_timeout_sec = OLLAMA_TIMEOUT_SEC
        self.ollama_keep_alive = OLLAMA_KEEP_ALIVE
        self.ollama_temperature = self._safe_float(OLLAMA_TEMPERATURE_RAW, default=0.2)
        self.ollama_tools = [self._to_ollama_tool(fn) for fn in AGENT_FUNCTIONS]
        self.ollama_auto_start = OLLAMA_AUTO_START
        self.ollama_auto_pull = OLLAMA_AUTO_PULL
        self.ollama_startup_timeout_sec = max(5, OLLAMA_STARTUP_TIMEOUT_SEC)
        self.ollama_pull_timeout_sec = max(60, OLLAMA_PULL_TIMEOUT_SEC)
        self.require_manual_auth = WEB_AGENT_REQUIRE_MANUAL_AUTH
        self.confirm_destructive_actions = WEB_AGENT_CONFIRM_DESTRUCTIVE_ACTIONS
        self.confirm_sensitive_actions = WEB_AGENT_CONFIRM_SENSITIVE_ACTIONS
        self.confirm_high_risk_domain_mutation = WEB_AGENT_CONFIRM_HIGH_RISK_DOMAIN_MUTATION
        self.confirm_high_risk_navigation = WEB_AGENT_CONFIRM_HIGH_RISK_NAVIGATION
        self.confirmation_cache_ttl_sec = WEB_AGENT_CONFIRMATION_CACHE_TTL_SEC
        self.browser_mode = WEB_AGENT_BROWSER_MODE if WEB_AGENT_BROWSER_MODE in {"managed", "cdp"} else "managed"
        self.cdp_url = WEB_AGENT_CDP_URL
        self.cdp_reuse_page = WEB_AGENT_CDP_REUSE_PAGE
        self._approval_cache: Dict[str, float] = {}
        self._manual_auth_approved_realms: set[str] = set()
        self._awaiting_manual_auth_completion = False
        self._manual_auth_realm = ""
        self._ollama_ready = False
        self._ollama_bootstrap_lock = asyncio.Lock()

    @staticmethod
    def _truthy(raw: Optional[str]) -> bool:
        if raw is None:
            return False
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _clamp(value: int, low: int, high: int) -> int:
        return max(low, min(high, value))

    @staticmethod
    def _normalize_url(url: str) -> str:
        raw = str(url or "").strip()
        if not raw:
            return DEFAULT_START_URL
        parsed = urlparse(raw)
        if parsed.scheme:
            return raw
        return f"https://{raw}"

    @staticmethod
    def _compact_text(text: str, limit: int = 2000) -> str:
        normalized = " ".join(str(text or "").split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 3)] + "..."

    async def _notify(self, update_callback: Optional[Any], message: str) -> None:
        if not update_callback or not message:
            return
        try:
            await update_callback(None, message)
        except Exception:
            pass

    def _is_local_ollama_endpoint(self) -> bool:
        parsed = urlparse(self.ollama_base_url)
        host = (parsed.hostname or "").strip().lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    def _fetch_ollama_tags_sync(self) -> Dict[str, Any]:
        url = f"{self.ollama_base_url}/api/tags"
        req = urllib.request.Request(url=url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    async def _is_ollama_reachable(self) -> bool:
        try:
            await asyncio.to_thread(self._fetch_ollama_tags_sync)
            return True
        except Exception:
            return False

    async def _wait_for_ollama(self, timeout_sec: float) -> bool:
        deadline = time.monotonic() + max(0.1, timeout_sec)
        while time.monotonic() < deadline:
            if await self._is_ollama_reachable():
                return True
            await asyncio.sleep(0.5)
        return await self._is_ollama_reachable()

    @staticmethod
    def _normalize_model_name(model_id: str) -> str:
        return str(model_id or "").strip().lower()

    @classmethod
    def _model_name_variants(cls, model_id: str) -> List[str]:
        normalized = cls._normalize_model_name(model_id)
        if not normalized:
            return []
        variants = {normalized}
        if ":" in normalized:
            base, tag = normalized.split(":", 1)
            if tag == "latest":
                variants.add(base)
        else:
            variants.add(f"{normalized}:latest")
        return list(variants)

    def _extract_installed_models(self, tags_payload: Dict[str, Any]) -> List[str]:
        models = tags_payload.get("models") if isinstance(tags_payload, dict) else []
        if not isinstance(models, list):
            return []
        names: List[str] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            for key in ("name", "model"):
                value = self._normalize_model_name(str(model.get(key) or ""))
                if value:
                    names.append(value)
        return names

    def _is_model_installed(self, installed_models: List[str], model_id: str) -> bool:
        if not installed_models:
            return False
        installed = set(installed_models)
        variants = self._model_name_variants(model_id)
        return any(v in installed for v in variants)

    def _start_ollama_serve_sync(self) -> None:
        kwargs: Dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            flags = 0
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
            flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if flags:
                kwargs["creationflags"] = flags
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(["ollama", "serve"], **kwargs)

    def _pull_model_sync(self, model_id: str) -> None:
        proc = subprocess.run(
            ["ollama", "pull", model_id],
            capture_output=True,
            text=True,
            timeout=self.ollama_pull_timeout_sec,
            check=False,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            detail = stderr or stdout or f"exit code {proc.returncode}"
            raise RuntimeError(f"ollama pull {model_id} failed: {detail}")

    async def _ensure_ollama_ready(self, update_callback: Optional[Any] = None) -> None:
        if self._ollama_ready:
            if await self._is_ollama_reachable():
                return
            self._ollama_ready = False

        async with self._ollama_bootstrap_lock:
            if self._ollama_ready:
                if await self._is_ollama_reachable():
                    return
                self._ollama_ready = False

            if not await self._wait_for_ollama(1.5):
                if not self.ollama_auto_start:
                    raise RuntimeError(
                        f"Ollama is not reachable at {self.ollama_base_url}. "
                        "Enable WEB_AGENT_OLLAMA_AUTO_START=1 or start it manually with `ollama serve`."
                    )
                if not self._is_local_ollama_endpoint():
                    raise RuntimeError(
                        f"Ollama is not reachable at non-local endpoint {self.ollama_base_url}. "
                        "Auto-start works only for local endpoints."
                    )

                await self._notify(update_callback, "Ollama not detected. Starting local Ollama in background...")
                try:
                    await asyncio.to_thread(self._start_ollama_serve_sync)
                except FileNotFoundError:
                    raise RuntimeError("`ollama` command not found. Install Ollama and add it to PATH.")
                except Exception as e:
                    raise RuntimeError(f"Failed to start Ollama: {e}")

                started = await self._wait_for_ollama(self.ollama_startup_timeout_sec)
                if not started:
                    raise RuntimeError(
                        f"Ollama did not become ready at {self.ollama_base_url} within "
                        f"{self.ollama_startup_timeout_sec}s."
                    )
                await self._notify(update_callback, "Ollama is running.")

            required_models: List[str] = [self.model_id]
            if self.planner_model_id and self.planner_model_id != self.model_id:
                required_models.append(self.planner_model_id)

            try:
                tags_payload = await asyncio.to_thread(self._fetch_ollama_tags_sync)
            except Exception as e:
                raise RuntimeError(f"Failed to query Ollama models: {e}")

            installed_models = self._extract_installed_models(tags_payload)
            for required_model in required_models:
                if self._is_model_installed(installed_models, required_model):
                    continue

                if not self.ollama_auto_pull:
                    raise RuntimeError(
                        f"Ollama model '{required_model}' not found. "
                        f"Run: ollama pull {required_model}"
                    )
                if not self._is_local_ollama_endpoint():
                    raise RuntimeError(
                        f"Ollama model '{required_model}' not found on remote endpoint {self.ollama_base_url}. "
                        "Auto-pull is disabled for non-local endpoints."
                    )

                await self._notify(
                    update_callback,
                    f"Ollama model '{required_model}' not found. Pulling it now...",
                )
                try:
                    await asyncio.to_thread(self._pull_model_sync, required_model)
                except FileNotFoundError:
                    raise RuntimeError("`ollama` command not found. Install Ollama and add it to PATH.")
                except subprocess.TimeoutExpired:
                    raise RuntimeError(
                        f"Timeout while pulling Ollama model '{required_model}' "
                        f"(>{self.ollama_pull_timeout_sec}s)."
                    )
                except Exception as e:
                    raise RuntimeError(str(e))

                tags_payload = await asyncio.to_thread(self._fetch_ollama_tags_sync)
                installed_models = self._extract_installed_models(tags_payload)
                if not self._is_model_installed(installed_models, required_model):
                    raise RuntimeError(
                        f"Ollama model '{required_model}' still not available after pull."
                    )
                await self._notify(update_callback, f"Ollama model '{required_model}' is ready.")

            self._ollama_ready = True

    @staticmethod
    def _normalize_json_schema(node: Any) -> Any:
        if isinstance(node, list):
            return [WebAgent._normalize_json_schema(item) for item in node]
        if isinstance(node, dict):
            normalized: Dict[str, Any] = {}
            for k, v in node.items():
                if k == "type" and isinstance(v, str):
                    normalized[k] = v.lower()
                else:
                    normalized[k] = WebAgent._normalize_json_schema(v)
            return normalized
        return node

    @classmethod
    def _to_ollama_tool(cls, decl: Dict[str, Any]) -> Dict[str, Any]:
        params = decl.get("parameters") or {"type": "object", "properties": {}}
        params = cls._normalize_json_schema(params)
        return {
            "type": "function",
            "function": {
                "name": str(decl.get("name") or "").strip(),
                "description": str(decl.get("description") or "").strip(),
                "parameters": params,
            },
        }

    async def _extract_links(self, limit: int = 20) -> List[Dict[str, str]]:
        lim = self._clamp(self._safe_int(limit, 20), 1, 100)
        js = """
        (maxLinks) => {
          const links = [];
          const seen = new Set();
          for (const a of Array.from(document.querySelectorAll('a[href]'))) {
            const href = (a.href || '').trim();
            if (!href || seen.has(href)) continue;
            seen.add(href);
            const text = ((a.innerText || a.textContent || '') + '').trim();
            links.push({ text: text.slice(0, 140), href });
            if (links.length >= maxLinks) break;
          }
          return links;
        }
        """
        data = await self.page.evaluate(js, lim)
        if not isinstance(data, list):
            return []
        out: List[Dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            href = str(item.get("href", "")).strip()
            if not href:
                continue
            out.append({"text": str(item.get("text", "")).strip(), "href": href})
        return out

    async def _page_text_excerpt(self, max_chars: int = 2000) -> str:
        limit = self._clamp(self._safe_int(max_chars, 2000), 200, 8000)
        text = await self.page.evaluate("() => (document.body ? document.body.innerText || '' : '')")
        return self._compact_text(text, limit=limit)

    async def _get_page_snapshot(self, max_chars: int = 2000) -> Dict[str, Any]:
        try:
            title = await self.page.title()
        except Exception:
            title = ""
        links = await self._extract_links(limit=8)
        return {
            "url": self.page.url,
            "title": title,
            "text_excerpt": await self._page_text_excerpt(max_chars=max_chars),
            "top_links": links,
        }

    def _ollama_chat_sync(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": OLLAMA_THINK,
        }
        if tools:
            payload["tools"] = tools
        if self.ollama_keep_alive:
            payload["keep_alive"] = self.ollama_keep_alive
        if self.ollama_temperature is not None:
            payload["options"] = {"temperature": self.ollama_temperature}

        url = f"{self.ollama_base_url}/api/chat"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.ollama_timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            detail = body
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict) and parsed.get("error"):
                    detail = str(parsed.get("error"))
            except Exception:
                pass
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama connection error: {e}")

        try:
            parsed = json.loads(raw)
        except Exception:
            raise RuntimeError(f"Invalid JSON from Ollama: {raw[:500]}")

        if isinstance(parsed, dict) and parsed.get("error"):
            raise RuntimeError(f"Ollama error: {parsed.get('error')}")
        return parsed if isinstance(parsed, dict) else {}

    async def _ollama_chat(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._ollama_chat_sync,
            messages=messages,
            model=model,
            tools=tools,
        )

    async def _build_plan(self, prompt: str) -> List[str]:
        task = str(prompt or "").strip()
        if not task:
            return [
                "Open relevant webpage.",
                "Collect key information.",
                "Cross-check important details.",
                "Prepare concise final answer.",
            ]
        try:
            plan_prompt = (
                "Create a short actionable browser-task plan. "
                "Return ONLY valid JSON: {\"steps\":[\"...\",\"...\"]}. "
                "Use 3-6 steps, imperative verbs, no markdown.\n\n"
                f"Task: {task}"
            )
            resp = await self._ollama_chat(
                messages=[{"role": "user", "content": plan_prompt}],
                model=self.planner_model_id,
                tools=None,
            )
            message = resp.get("message") if isinstance(resp, dict) else {}
            raw = str((message or {}).get("content") or "").strip()
            if raw:
                start = raw.find("{")
                end = raw.rfind("}")
                if start != -1 and end > start:
                    raw = raw[start : end + 1]
                obj = json.loads(raw)
                steps = obj.get("steps") if isinstance(obj, dict) else None
                if isinstance(steps, list):
                    cleaned = [self._compact_text(str(s), 120) for s in steps if str(s).strip()]
                    if cleaned:
                        return cleaned[:6]
        except Exception:
            pass

        words = task.split()
        focus = " ".join(words[:6]) if words else "task"
        return [
            f"Open source relevant to: {focus}.",
            "Find exact information needed for the user.",
            "Validate with at least one additional signal on page.",
            "Summarize result with key facts only.",
        ]

    def _is_sensitive_action(self, fn_name: str, args: Dict[str, Any]) -> bool:
        if fn_name not in {"click_selector", "type_selector", "press_key", "navigate"}:
            return False
        haystack = " ".join(
            [
                fn_name,
                str(args.get("selector", "")),
                str(args.get("text", "")),
                str(args.get("url", "")),
                str(args.get("keys", "")),
            ]
        ).lower()
        return any(keyword in haystack for keyword in SENSITIVE_ACTION_KEYWORDS)

    def _is_manual_auth_step(self, fn_name: str, args: Dict[str, Any]) -> bool:
        if fn_name != "type_selector":
            return False
        haystack = " ".join(
            [
                fn_name,
                str(args.get("selector", "")),
                str(args.get("text", "")),
                str(args.get("url", "")),
                str(args.get("keys", "")),
                self.page.url if self.page else "",
            ]
        ).lower()
        return any(keyword in haystack for keyword in AUTH_FLOW_HINT_KEYWORDS)

    @staticmethod
    def _extract_host(url: str) -> str:
        try:
            return (urlparse(str(url or "")).hostname or "").strip().lower()
        except Exception:
            return ""

    @staticmethod
    def _host_realm(host: str) -> str:
        raw = str(host or "").strip().lower().strip(".")
        if not raw:
            return ""
        if raw in {"localhost", "127.0.0.1", "::1"}:
            return raw
        parts = [p for p in raw.split(".") if p]
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return raw

    @staticmethod
    def _contains_any(haystack: str, keywords: set) -> bool:
        text = str(haystack or "").lower()
        return any(keyword in text for keyword in keywords)

    def _is_high_risk_host(self, host: str) -> bool:
        return self._contains_any(host, HIGH_RISK_DOMAIN_KEYWORDS)

    def _action_text_haystack(self, fn_name: str, args: Dict[str, Any]) -> str:
        return " ".join(
            [
                str(fn_name or ""),
                str(args.get("selector", "")),
                str(args.get("text", "")),
                str(args.get("url", "")),
                str(args.get("keys", "")),
                self.page.url if self.page else "",
            ]
        ).lower()

    def _policy_cache_key(self, action: str, args: Dict[str, Any], policy: Dict[str, Any]) -> str:
        host = str(policy.get("target_host") or policy.get("current_host") or "").strip().lower()
        realm = self._host_realm(host)
        reason_code = str(policy.get("reason_code") or "confirmation_required").strip().lower()
        if bool(policy.get("manual_gate")):
            return f"{reason_code}:{realm or host}"
        selector = str(args.get("selector") or "").strip().lower()[:120]
        keys = str(args.get("keys") or "").strip().lower()[:120]
        return f"{reason_code}:{str(action or '').strip().lower()}:{host}:{selector}:{keys}"

    def _policy_realm(self, policy: Dict[str, Any]) -> str:
        host = str(policy.get("target_host") or policy.get("current_host") or "").strip().lower()
        return self._host_realm(host)

    @staticmethod
    def _is_auth_page_url(url: str) -> bool:
        raw = str(url or "").strip().lower()
        if not raw:
            return False
        host = (urlparse(raw).hostname or "").strip().lower()
        path = (urlparse(raw).path or "").strip().lower()
        auth_host_markers = {"accounts.google.com", "login.", "signin.", "auth."}
        auth_path_markers = {
            "/signin",
            "/login",
            "/identifier",
            "/challenge",
            "/auth",
            "/verify",
            "/2fa",
            "/saml",
        }
        if any(marker in host for marker in auth_host_markers):
            return True
        return any(marker in path for marker in auth_path_markers)

    def _refresh_manual_auth_state(self) -> None:
        if not self._awaiting_manual_auth_completion:
            return
        current_url = self.page.url if self.page else ""
        current_host = self._extract_host(current_url)
        current_realm = self._host_realm(current_host)
        still_auth_page = self._is_auth_page_url(current_url)
        same_realm = (not self._manual_auth_realm) or (current_realm == self._manual_auth_realm)
        if still_auth_page and same_realm:
            return
        self._awaiting_manual_auth_completion = False
        self._manual_auth_realm = ""

    def _is_confirmation_cached(self, key: str) -> bool:
        ttl = max(0, int(self.confirmation_cache_ttl_sec))
        if ttl <= 0:
            return False
        ts = self._approval_cache.get(str(key))
        if ts is None:
            return False
        if (time.monotonic() - ts) <= ttl:
            return True
        self._approval_cache.pop(str(key), None)
        return False

    def _mark_confirmation_cached(self, key: str) -> None:
        ttl = max(0, int(self.confirmation_cache_ttl_sec))
        if ttl <= 0:
            return
        self._approval_cache[str(key)] = time.monotonic()

    def _build_action_policy(self, fn_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        action = str(fn_name or "").strip()
        current_url = self.page.url if self.page else ""
        current_host = self._extract_host(current_url)
        target_url = ""
        target_host = ""
        if action == "navigate":
            target_url = self._normalize_url(args.get("url", ""))
            target_host = self._extract_host(target_url)

        host_for_risk = target_host or current_host
        haystack = self._action_text_haystack(action, args)
        is_auth = self._is_manual_auth_step(action, args)
        is_destructive = self._contains_any(haystack, DESTRUCTIVE_ACTION_KEYWORDS)
        is_sensitive_text = self._is_sensitive_action(action, args)
        high_risk_domain = self._is_high_risk_host(host_for_risk)
        is_mutating_action = action in {"navigate", "click_selector", "type_selector", "press_key"}

        requires_confirmation = False
        manual_gate = False
        reason_code = ""
        reason = ""

        if self.require_manual_auth and is_auth:
            requires_confirmation = True
            manual_gate = True
            reason_code = "manual_auth_step"
            reason = (
                "Manual login/auth step required. Enter credentials/2FA directly in browser, "
                "then click Allow."
            )
        elif self.enable_sensitive_approvals and is_mutating_action:
            if self.confirm_destructive_actions and is_destructive:
                requires_confirmation = True
                reason_code = "destructive_action"
                reason = "Potentially destructive action detected."
            elif (
                self.confirm_high_risk_domain_mutation
                and high_risk_domain
                and action in {"click_selector", "type_selector", "press_key"}
            ):
                requires_confirmation = True
                reason_code = "high_risk_domain_mutation"
                reason = f"Action modifies data on high-risk domain '{host_for_risk}'."
            elif self.confirm_high_risk_navigation and high_risk_domain and action == "navigate":
                requires_confirmation = True
                reason_code = "high_risk_navigation"
                reason = f"Navigation to high-risk domain '{host_for_risk}'."
            elif self.confirm_sensitive_actions and is_sensitive_text:
                requires_confirmation = True
                reason_code = "sensitive_action"
                reason = "Sensitive web action detected."

        return {
            "requires_confirmation": requires_confirmation,
            "manual_gate": manual_gate,
            "reason_code": reason_code,
            "reason": reason,
            "current_url": current_url,
            "current_host": current_host,
            "target_url": target_url,
            "target_host": target_host,
            "high_risk_domain": high_risk_domain,
            "is_destructive": is_destructive,
            "is_auth": is_auth,
        }

    @staticmethod
    def _normalize_call_payload(call: Any) -> Tuple[Optional[str], str, Dict[str, Any]]:
        call_id: Optional[str] = None
        fn_name = ""
        args: Dict[str, Any] = {}

        if isinstance(call, dict):
            call_id = call.get("id") or call.get("tool_call_id")
            fn_obj = call.get("function") if isinstance(call.get("function"), dict) else call
            if isinstance(fn_obj, dict):
                fn_name = str(fn_obj.get("name") or "").strip()
                raw_args = fn_obj.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except Exception:
                        raw_args = {}
                if isinstance(raw_args, dict):
                    args = raw_args
        else:
            call_id = getattr(call, "id", None)
            fn_name = str(getattr(call, "name", "")).strip()
            raw_args = getattr(call, "args", {}) or {}
            if isinstance(raw_args, dict):
                args = raw_args

        return call_id, fn_name, args

    async def execute_function_calls(
        self,
        function_calls: List[Any],
        action_approval_callback: Optional[Any] = None,
        cancel_event: Optional[asyncio.Event] = None,
        update_callback: Optional[Any] = None,
    ) -> List[Tuple[Optional[str], str, Dict[str, Any]]]:
        results: List[Tuple[Optional[str], str, Dict[str, Any]]] = []

        for call in function_calls:
            if cancel_event and cancel_event.is_set():
                results.append((None, "cancelled", {"cancelled": True, "reason": "job cancelled"}))
                break

            call_id, fn_name, args = self._normalize_call_payload(call)
            if not fn_name:
                results.append((call_id, "unknown", {"error": "missing function name"}))
                continue

            print(f"[ACTION] Action: {fn_name} {args}")
            result_data: Dict[str, Any] = {}
            try:
                self._refresh_manual_auth_state()
                if self._awaiting_manual_auth_completion and fn_name in {
                    "navigate",
                    "click_selector",
                    "type_selector",
                    "press_key",
                }:
                    result_data = {
                        "blocked_by_policy": True,
                        "reason_code": "awaiting_manual_auth_completion",
                        "reason": (
                            "Waiting for user to complete login/2FA in browser. "
                            "Automation is paused for mutating actions."
                        ),
                        "needs_user_intervention": True,
                    }
                    results.append((call_id, fn_name, result_data))
                    continue

                policy = self._build_action_policy(fn_name, args)
                if policy.get("requires_confirmation"):
                    realm = self._policy_realm(policy)
                    cache_key = self._policy_cache_key(fn_name, args, policy)
                    if policy.get("manual_gate"):
                        if realm and realm in self._manual_auth_approved_realms:
                            approved = True
                        else:
                            await self._notify(
                                update_callback,
                                "Manual login/2FA step required. Complete it in browser, then click Allow.",
                            )
                            approved = self._is_confirmation_cached(cache_key)
                    else:
                        approved = self._is_confirmation_cached(cache_key)
                    if not approved and action_approval_callback:
                        approval_payload = {
                            "action": "manual_auth_step" if policy.get("manual_gate") else fn_name,
                            "args": args,
                            "url": self.page.url if self.page else "",
                            "reason": policy.get("reason"),
                            "reason_code": policy.get("reason_code"),
                            "policy": {
                                "reason_code": policy.get("reason_code"),
                                "manual_gate": bool(policy.get("manual_gate")),
                                "high_risk_domain": bool(policy.get("high_risk_domain")),
                                "is_destructive": bool(policy.get("is_destructive")),
                                "current_host": policy.get("current_host"),
                                "target_host": policy.get("target_host"),
                            },
                        }
                        try:
                            approved = bool(await action_approval_callback(approval_payload))
                        except Exception:
                            approved = False
                    if approved:
                        self._mark_confirmation_cached(cache_key)
                    if not approved:
                        result_data = {
                            "blocked_by_policy": True,
                            "reason_code": policy.get("reason_code") or "confirmation_required",
                            "reason": (
                                "Manual login/2FA step required and not confirmed by user."
                                if policy.get("manual_gate")
                                else "Action requires explicit user confirmation."
                            ),
                        }
                        if policy.get("manual_gate"):
                            result_data["needs_user_intervention"] = True
                        results.append((call_id, fn_name, result_data))
                        continue
                    if policy.get("manual_gate"):
                        if realm:
                            self._manual_auth_approved_realms.add(realm)
                        self._awaiting_manual_auth_completion = True
                        self._manual_auth_realm = realm
                        result_data = {
                            "manual_user_step_completed": True,
                            "reason_code": policy.get("reason_code") or "manual_auth_step",
                            "reason": (
                                "User acknowledged manual login/2FA step. "
                                "Waiting for page to leave auth flow."
                            ),
                        }
                        results.append((call_id, fn_name, result_data))
                        continue

                if fn_name == "navigate":
                    url = self._normalize_url(args.get("url", ""))
                    await self.page.goto(url, wait_until="domcontentloaded")
                    result_data["url"] = self.page.url
                elif fn_name == "go_back":
                    await self.page.go_back()
                elif fn_name == "go_forward":
                    await self.page.go_forward()
                elif fn_name == "search":
                    query = str(args.get("query") or args.get("text") or "").strip()
                    if query:
                        await self.page.goto(f"https://www.google.com/search?q={quote_plus(query)}")
                    else:
                        await self.page.goto("https://www.google.com")
                elif fn_name == "wait_5_seconds":
                    await asyncio.sleep(5)
                elif fn_name == "click_selector":
                    selector = str(args.get("selector") or "").strip()
                    index = self._clamp(self._safe_int(args.get("index"), 0), 0, 200)
                    if not selector:
                        raise ValueError("selector required")
                    locator = self.page.locator(selector).nth(index)
                    await locator.click(timeout=10000)
                elif fn_name == "type_selector":
                    selector = str(args.get("selector") or "").strip()
                    text = str(args.get("text") or "")
                    press_enter = bool(args.get("press_enter", False))
                    clear_before = bool(args.get("clear_before_typing", True))
                    if not selector:
                        raise ValueError("selector required")
                    locator = self.page.locator(selector).first
                    await locator.click(timeout=10000)
                    if clear_before:
                        await locator.fill("")
                    await locator.type(text, delay=10)
                    if press_enter:
                        await self.page.keyboard.press("Enter")
                elif fn_name == "wait_for_selector":
                    selector = str(args.get("selector") or "").strip()
                    timeout_ms = self._clamp(self._safe_int(args.get("timeout_ms"), 10000), 500, 60000)
                    if not selector:
                        raise ValueError("selector required")
                    await self.page.wait_for_selector(selector, timeout=timeout_ms)
                elif fn_name == "extract_links":
                    limit = self._safe_int(args.get("limit"), 20)
                    links = await self._extract_links(limit=limit)
                    result_data["links"] = links
                    result_data["count"] = len(links)
                elif fn_name == "get_page_snapshot":
                    max_chars = self._safe_int(args.get("max_chars"), 2000)
                    result_data.update(await self._get_page_snapshot(max_chars=max_chars))
                elif fn_name == "press_key":
                    key_comb = str(args.get("keys") or "").strip()
                    if key_comb:
                        await self.page.keyboard.press(key_comb)
                elif fn_name == "scroll_document":
                    magnitude = self._clamp(self._safe_int(args.get("magnitude"), 800), 50, 3000)
                    direction = str(args.get("direction", "down")).strip().lower()
                    dx, dy = 0, 0
                    if direction == "down":
                        dy = magnitude
                    elif direction == "up":
                        dy = -magnitude
                    elif direction == "right":
                        dx = magnitude
                    elif direction == "left":
                        dx = -magnitude
                    await self.page.mouse.wheel(dx, dy)
                elif fn_name == "finish_task":
                    if self._awaiting_manual_auth_completion:
                        result_data = {
                            "blocked_by_policy": True,
                            "reason_code": "awaiting_manual_auth_completion",
                            "reason": (
                                "Cannot finish task while manual login/2FA is still pending. "
                                "Wait for auth completion and verify post-login page first."
                            ),
                            "needs_user_intervention": True,
                        }
                        results.append((call_id, fn_name, result_data))
                        continue
                    summary = self._compact_text(str(args.get("summary") or "").strip(), limit=2000)
                    self._finish_requested = True
                    self._finish_summary = summary or "Task finished."
                    result_data["done"] = True
                    result_data["summary"] = self._finish_summary
                else:
                    result_data = {"error": f"Unknown function '{fn_name}'"}

                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[ERR] Error executing {fn_name}: {e}")
                result_data = {"error": str(e)}

            results.append((call_id, fn_name, result_data))

        return results

    async def get_function_responses(
        self, results: List[Tuple[Optional[str], str, Dict[str, Any]]]
    ) -> Tuple[List[Dict[str, Any]], bytes]:
        screenshot_bytes = b""
        current_url = ""
        screenshot_error = ""
        try:
            if self.page and (not self.page.is_closed()):
                screenshot_bytes = await self.page.screenshot(type="png")
                current_url = self.page.url
            else:
                screenshot_error = "page is closed"
        except Exception as e:
            screenshot_error = str(e)
            try:
                if self.page and (not self.page.is_closed()):
                    current_url = self.page.url
            except Exception:
                current_url = ""

        tool_messages: List[Dict[str, Any]] = []
        for call_id, name, result in results:
            response_data = {"url": current_url}
            response_data.update(result)
            if screenshot_error:
                response_data["screenshot_error"] = screenshot_error
            msg: Dict[str, Any] = {
                "role": "tool",
                "tool_name": str(name or ""),
                "content": json.dumps(response_data, ensure_ascii=False),
            }
            if call_id:
                msg["tool_call_id"] = str(call_id)
            tool_messages.append(msg)
        return tool_messages, screenshot_bytes

    def _normalize_ollama_response(self, response: Dict[str, Any]) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]]]:
        message = response.get("message") if isinstance(response, dict) else None
        if not isinstance(message, dict):
            raise RuntimeError(f"Invalid Ollama response shape: {response}")
        content = str(message.get("content") or "").strip()
        tool_calls = message.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            tool_calls = []
        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        return assistant_msg, content, tool_calls

    async def run_task(
        self,
        prompt: str,
        update_callback: Optional[Any] = None,
        action_approval_callback: Optional[Any] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> str:
        print(f"[START] Monika OpenClaw fork started (ollama). Goal: {prompt}")
        final_response = "Agent finished without a final summary."
        self._finish_requested = False
        self._finish_summary = ""
        self._approval_cache.clear()
        self._manual_auth_approved_realms.clear()
        self._awaiting_manual_auth_completion = False
        self._manual_auth_realm = ""
        recent_actions: List[str] = []
        plan_steps: List[str] = []
        owns_browser = True
        created_page = False
        created_context = False
        should_bootstrap_start_page = True

        try:
            await self._ensure_ollama_ready(update_callback=update_callback)
            plan_steps = await self._build_plan(str(prompt or ""))

            async with async_playwright() as p:
                if self.browser_mode == "cdp":
                    self.browser = await p.chromium.connect_over_cdp(self.cdp_url)
                    owns_browser = False
                    if update_callback:
                        await update_callback(None, f"Attached to existing browser via CDP: {self.cdp_url}")
                    existing_contexts = list(self.browser.contexts or [])
                    if existing_contexts:
                        self.context = existing_contexts[0]
                    else:
                        self.context = await self.browser.new_context(
                            viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT},
                        )
                        created_context = True
                    if self.cdp_reuse_page and self.context.pages:
                        self.page = self.context.pages[0]
                        should_bootstrap_start_page = False
                    else:
                        self.page = await self.context.new_page()
                        created_page = True
                else:
                    self.browser = await p.chromium.launch(headless=self.headless)
                    owns_browser = True
                    self.context = await self.browser.new_context(
                        viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT},
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    )
                    self.page = await self.context.new_page()
                    created_page = True
                if should_bootstrap_start_page:
                    await self.page.goto(DEFAULT_START_URL, wait_until="domcontentloaded")

                initial_screenshot = await self.page.screenshot(type="png")
                initial_snapshot = await self._get_page_snapshot(max_chars=1600)
                if update_callback:
                    encoded_image = base64.b64encode(initial_screenshot).decode("utf-8")
                    await update_callback(encoded_image, "Monika OpenClaw fork initialized (ollama).")
                    plan_text = "\n".join([f"{idx + 1}. {step}" for idx, step in enumerate(plan_steps)])
                    await update_callback(None, f"Plan:\n{plan_text}")

                tool_names = ", ".join([fn["name"] for fn in AGENT_FUNCTIONS])
                system_prompt = (
                    "You are a browser automation agent for Monika. "
                    "Use available tools to complete the task safely and efficiently. "
                    "Always call finish_task(summary=...) when the task is complete. "
                    "If login/2FA is required, ask user to complete it and continue. "
                    "After a manual auth confirmation, do not keep trying credential-entry actions repeatedly. "
                    "Wait/check page state and proceed only after login is complete. "
                    "Never enter credentials, passwords, OTP codes, or private auth data yourself.\n\n"
                    f"Available tools: {tool_names}"
                )
                user_prompt = (
                    f"Task: {prompt}\n\n"
                    "Current page snapshot JSON:\n"
                    f"{json.dumps(initial_snapshot, ensure_ascii=False)}\n\n"
                    "Prefer deterministic selector tools and page snapshot tools."
                )
                messages: List[Dict[str, Any]] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]

                for turn in range(self.max_turns):
                    print(f"\n--- Turn {turn + 1} ---")
                    if cancel_event and cancel_event.is_set():
                        final_response = "Task cancelled by user."
                        if update_callback:
                            await update_callback(None, "Task cancelled.")
                        break

                    response = await self._ollama_chat(
                        messages=messages,
                        model=self.model_id,
                        tools=self.ollama_tools,
                    )
                    assistant_msg, assistant_content, tool_calls = self._normalize_ollama_response(response)
                    messages.append(assistant_msg)

                    if assistant_content:
                        final_response = assistant_content

                    if not tool_calls:
                        if self._awaiting_manual_auth_completion:
                            if update_callback:
                                await update_callback(
                                    None,
                                    "Waiting for manual login/2FA in browser window. Complete it, then agent will continue.",
                                )
                            try:
                                waiting_snapshot = await self._get_page_snapshot(max_chars=1200)
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            "Manual auth may still be pending. Do NOT finish task yet. "
                                            "Wait and re-check page state until auth flow is completed.\n\n"
                                            "Current page snapshot JSON:\n"
                                            f"{json.dumps(waiting_snapshot, ensure_ascii=False)}"
                                        ),
                                    }
                                )
                            except Exception:
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            "Manual auth may still be pending. Do NOT finish task yet. "
                                            "Use wait_5_seconds, then verify page state."
                                        ),
                                    }
                                )
                            await asyncio.sleep(1.0)
                            continue
                        if self._finish_requested and self._finish_summary:
                            final_response = self._finish_summary
                        if update_callback:
                            await update_callback(None, "Task finished.")
                        break

                    results = await self.execute_function_calls(
                        tool_calls,
                        action_approval_callback=action_approval_callback,
                        cancel_event=cancel_event,
                        update_callback=update_callback,
                    )

                    for _, name, data in results:
                        recent_actions.append(name)
                        if len(recent_actions) > 12:
                            recent_actions = recent_actions[-12:]
                        if name == "finish_task" and isinstance(data, dict):
                            summary = str(data.get("summary") or "").strip()
                            if summary:
                                final_response = summary
                        if isinstance(data, dict) and data.get("cancelled"):
                            final_response = "Task cancelled by user."

                    if final_response == "Task cancelled by user.":
                        if update_callback:
                            await update_callback(None, "Task cancelled before next checkpoint.")
                        break

                    if update_callback and plan_steps:
                        step_idx = min(turn, len(plan_steps) - 1)
                        await update_callback(
                            None,
                            f"Checkpoint {step_idx + 1}/{len(plan_steps)}: {plan_steps[step_idx]}",
                        )

                    print("[SNAP] Capturing new state...")
                    tool_messages, screenshot_bytes = await self.get_function_responses(results)
                    messages.extend(tool_messages)

                    if update_callback:
                        actions_log = ", ".join([r[1] for r in results])
                        if screenshot_bytes:
                            encoded_image = base64.b64encode(screenshot_bytes).decode("utf-8")
                            await update_callback(encoded_image, f"Executed: {actions_log}")
                        else:
                            await update_callback(None, f"Executed: {actions_log} (no screenshot)")

                    if not self.page or self.page.is_closed():
                        final_response = "Task stopped because browser page was closed."
                        if update_callback:
                            await update_callback(None, final_response)
                        break

                    if len(recent_actions) >= 6 and recent_actions[-3:] == recent_actions[-6:-3]:
                        loop_msg = "Loop detected in repeated actions. Stopping with current best result."
                        print(f"[WARN] {loop_msg}")
                        if update_callback:
                            await update_callback(None, loop_msg)
                        break

                    if self._finish_requested:
                        if self._finish_summary:
                            final_response = self._finish_summary
                        print("[DONE] finish_task called.")
                        break

                if self._finish_requested and self._finish_summary:
                    final_response = self._finish_summary
                elif final_response == "Agent finished without a final summary.":
                    final_response = self._compact_text(
                        "Task ended without explicit final summary. Check browser logs for steps/results.",
                        300,
                    )

                if update_callback:
                    await update_callback(None, f"Final summary: {self._compact_text(final_response, 900)}")

                return final_response
        except Exception as e:
            msg = str(e)
            lower = msg.lower()
            if "executable doesn't exist" in lower and "playwright install" in lower:
                raise RuntimeError(
                    "Playwright browser is not installed for this Python environment. "
                    f"Run: {sys.executable} -m playwright install chromium"
                )
            if "ollama connection error" in lower:
                raise RuntimeError(
                    f"Ollama is not reachable at {self.ollama_base_url}. Start it with `ollama serve`."
                )
            if "model" in lower and "not found" in lower:
                raise RuntimeError(
                    f"Ollama model '{self.model_id}' not found. Run: ollama pull {self.model_id}"
                )
            if self.browser_mode == "cdp" and ("connect_over_cdp" in lower or "ws endpoint" in lower or "connection refused" in lower):
                raise RuntimeError(
                    "Failed to attach to existing browser via CDP. "
                    f"Start Chrome/Edge with remote debugging and verify WEB_AGENT_CDP_URL={self.cdp_url}."
                )
            raise
        finally:
            had_resources = bool(self.browser or self.context or self.page)
            try:
                if owns_browser:
                    if self.browser and getattr(self.browser, "is_connected", lambda: True)():
                        await self.browser.close()
                else:
                    if created_context and self.context:
                        await self.context.close()
                    elif created_page and self.page and (not self.page.is_closed()):
                        await self.page.close()
            except Exception:
                pass
            finally:
                if had_resources:
                    if owns_browser:
                        print("[CLOSE] Monika OpenClaw fork browser closed.")
                    else:
                        print("[CLOSE] Monika OpenClaw fork detached from existing browser.")
                self.page = None
                self.context = None
                self.browser = None

    async def run(self, prompt: str) -> str:
        return await self.run_task(prompt)


if __name__ == "__main__":
    agent = WebAgent()
    asyncio.run(agent.run_task("Go to google.com and search for latest Python release."))
