import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _strip_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _coerce_scalar(value: str) -> Any:
    text = _strip_quotes(str(value or "").strip())
    low = text.lower()
    if low in {"true", "yes", "on"}:
        return True
    if low in {"false", "no", "off"}:
        return False
    if low in {"null", "none", "~"}:
        return None
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except Exception:
            return text
    if re.fullmatch(r"-?\d+\.\d+", text):
        try:
            return float(text)
        except Exception:
            return text
    return text


def _current_os_alias() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("darwin"):
        return "macos"
    return "linux"


def _json_brace_balance(text: str) -> int:
    opens = text.count("{")
    closes = text.count("}")
    return opens - closes


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_json_comments(text: str) -> str:
    # Minimal JSONC/JSON5 comment stripping for skills runtime config files.
    out: List[str] = []
    in_string = False
    string_char = ""
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue
        if ch in {'"', "'"}:
            in_string = True
            string_char = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_json_trailing_commas(text: str) -> str:
    out: List[str] = []
    in_string = False
    string_char = ""
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue
        if ch in {'"', "'"}:
            in_string = True
            string_char = ch
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j < len(text) and text[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _load_json_loose(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    cleaned = _strip_json_trailing_commas(_strip_json_comments(raw))
    data = json.loads(cleaned)
    return data if isinstance(data, dict) else {}


def _parse_simple_yaml_block(lines: List[str], start_idx: int, indent: int) -> Tuple[Any, int]:
    mode: Optional[str] = None
    dict_out: Dict[str, Any] = {}
    list_out: List[Any] = []
    i = start_idx

    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue

        cur_indent = _leading_spaces(raw)
        if cur_indent < indent:
            break
        if cur_indent > indent:
            break

        stripped = raw.strip()
        if stripped.startswith("- "):
            if mode is None:
                mode = "list"
            elif mode != "list":
                break

            item_text = stripped[2:].strip()
            i += 1
            if not item_text:
                child, i = _parse_simple_yaml_block(lines, i, indent + 2)
                list_out.append(child)
                continue

            m = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", item_text)
            if m:
                item: Dict[str, Any] = {}
                key = m.group(1).strip()
                value = m.group(2).strip()
                if value in {"|", ">"}:
                    block_lines: List[str] = []
                    while i < len(lines):
                        nxt = lines[i]
                        if not nxt.strip():
                            block_lines.append("")
                            i += 1
                            continue
                        nxt_indent = _leading_spaces(nxt)
                        if nxt_indent < indent + 2:
                            break
                        block_lines.append(nxt[indent + 2 :])
                        i += 1
                    item[key] = "\n".join(block_lines).strip()
                elif value:
                    item[key] = _coerce_scalar(value)
                else:
                    child, i = _parse_simple_yaml_block(lines, i, indent + 2)
                    item[key] = child

                while i < len(lines):
                    peek = lines[i]
                    if not peek.strip() or peek.lstrip().startswith("#"):
                        i += 1
                        continue
                    peek_indent = _leading_spaces(peek)
                    if peek_indent < indent + 2 or peek.strip().startswith("- "):
                        break
                    if peek_indent > indent + 2:
                        break
                    sub = peek.strip()
                    m2 = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", sub)
                    if not m2:
                        i += 1
                        continue
                    sub_key = m2.group(1).strip()
                    sub_value = m2.group(2).strip()
                    i += 1
                    if sub_value in {"|", ">"}:
                        block_lines = []
                        while i < len(lines):
                            nxt = lines[i]
                            if not nxt.strip():
                                block_lines.append("")
                                i += 1
                                continue
                            nxt_indent = _leading_spaces(nxt)
                            if nxt_indent < indent + 4:
                                break
                            block_lines.append(nxt[indent + 4 :])
                            i += 1
                        item[sub_key] = "\n".join(block_lines).strip()
                    elif sub_value:
                        item[sub_key] = _coerce_scalar(sub_value)
                    else:
                        child, i = _parse_simple_yaml_block(lines, i, indent + 4)
                        item[sub_key] = child

                list_out.append(item)
            else:
                list_out.append(_coerce_scalar(item_text))
            continue

        if mode is None:
            mode = "dict"
        elif mode != "dict":
            break

        m = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", stripped)
        if not m:
            i += 1
            continue

        key = m.group(1).strip()
        value = m.group(2).strip()
        i += 1
        if value in {"|", ">"}:
            block_lines: List[str] = []
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    block_lines.append("")
                    i += 1
                    continue
                nxt_indent = _leading_spaces(nxt)
                if nxt_indent < indent + 2:
                    break
                block_lines.append(nxt[indent + 2 :])
                i += 1
            dict_out[key] = "\n".join(block_lines).strip()
        elif value:
            dict_out[key] = _coerce_scalar(value)
        else:
            child, i = _parse_simple_yaml_block(lines, i, indent + 2)
            dict_out[key] = child

    if mode == "list":
        return list_out, i
    return dict_out, i


@dataclass
class OpenClawSkill:
    name: str
    skill_key: str
    description: str
    path: Path
    body: str
    frontmatter: Dict[str, Any]
    metadata: Dict[str, Any]
    runtime_meta: Dict[str, Any]
    config_entry: Dict[str, Any]
    runtime_env: Dict[str, str]
    install_hints: List[Dict[str, Any]]
    eligible: bool
    eligibility_issues: List[str]
    disable_model_invocation: bool
    user_invocable: bool
    enabled: bool

    def to_summary(self) -> Dict[str, Any]:
        skill_dir = self.path.parent
        managed = False
        raw_managed_roots = self.metadata.get("_managed_roots")
        if not isinstance(raw_managed_roots, list):
            fallback_root = self.metadata.get("_managed_root")
            raw_managed_roots = [fallback_root] if fallback_root else []
        for root in raw_managed_roots:
            if not root:
                continue
            try:
                managed = str(skill_dir.resolve()).lower().startswith(str(Path(root).resolve()).lower())
            except Exception:
                managed = False
            if managed:
                break
        return {
            "name": self.name,
            "skill_key": self.skill_key,
            "description": self.description,
            "path": str(self.path),
            "directory": str(skill_dir),
            "managed": managed,
            "eligible": self.eligible,
            "eligibility_issues": list(self.eligibility_issues),
            "disable_model_invocation": self.disable_model_invocation,
            "user_invocable": self.user_invocable,
            "enabled": self.enabled,
            "runtime_env_keys": sorted(self.runtime_env.keys()),
            "install_hints": list(self.install_hints),
        }


class OpenClawSkillManager:
    def __init__(
        self,
        workspace_root: Path,
        env_var: str = "OPENCLAW_SKILLS_DIRS",
    ):
        self.workspace_root = Path(workspace_root)
        self.env_var = env_var
        self.managed_install_root = (self.workspace_root / "skills").resolve()
        self.project_agent_skills_root = (self.workspace_root / ".agents" / "skills").resolve()
        self.global_codex_skills_root = (Path.home() / ".codex" / "skills").resolve()
        self.global_agents_skills_root = (Path.home() / ".config" / "agents" / "skills").resolve()
        self.global_moltbot_skills_root = (Path.home() / ".moltbot" / "skills").resolve()
        self._skills_by_key: Dict[str, OpenClawSkill] = {}
        self._config_data: Dict[str, Any] = {}
        self.refresh()

    @staticmethod
    def _normalize_name(name: str) -> str:
        return str(name or "").strip().lower()

    def _candidate_roots(self) -> List[Path]:
        roots: List[Path] = []

        raw_env = str(os.getenv(self.env_var, "")).strip()
        if raw_env:
            for chunk in raw_env.split(os.pathsep):
                p = Path(chunk).expanduser()
                if p.exists() and p.is_dir():
                    roots.append(p)

        workspace_home_root = Path.home() / ".openclaw" / "workspace" / "skills"
        if workspace_home_root.exists() and workspace_home_root.is_dir():
            roots.append(workspace_home_root)

        agents_cfg = self._config_data.get("agents") if isinstance(self._config_data, dict) else {}
        if isinstance(agents_cfg, dict):
            defaults = agents_cfg.get("defaults")
            if isinstance(defaults, dict):
                cfg_workspace = str(defaults.get("workspace") or "").strip()
                if cfg_workspace:
                    cfg_workspace_skills = Path(cfg_workspace).expanduser() / "skills"
                    if cfg_workspace_skills.exists() and cfg_workspace_skills.is_dir():
                        roots.append(cfg_workspace_skills)

        home_root = Path.home() / ".openclaw" / "skills"
        if home_root.exists() and home_root.is_dir():
            roots.append(home_root)

        if self.global_moltbot_skills_root.exists() and self.global_moltbot_skills_root.is_dir():
            roots.append(self.global_moltbot_skills_root)

        if self.project_agent_skills_root.exists() and self.project_agent_skills_root.is_dir():
            roots.append(self.project_agent_skills_root)

        if self.global_codex_skills_root.exists() and self.global_codex_skills_root.is_dir():
            roots.append(self.global_codex_skills_root)

        if self.global_agents_skills_root.exists() and self.global_agents_skills_root.is_dir():
            roots.append(self.global_agents_skills_root)

        skills_cfg = self._config_data.get("skills") if isinstance(self._config_data, dict) else {}
        if isinstance(skills_cfg, dict):
            load_cfg = skills_cfg.get("load")
            if isinstance(load_cfg, dict):
                extra_dirs = load_cfg.get("extraDirs")
                if isinstance(extra_dirs, list):
                    for item in extra_dirs:
                        p = Path(str(item or "")).expanduser()
                        if p.exists() and p.is_dir():
                            roots.append(p)

        if self.managed_install_root.exists() and self.managed_install_root.is_dir():
            roots.append(self.managed_install_root)

        out: List[Path] = []
        seen = set()
        for root in roots:
            key = str(root.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(root)
        return out

    def _managed_roots(self) -> List[Path]:
        roots = [
            self.managed_install_root,
            self.project_agent_skills_root,
            self.global_codex_skills_root,
            self.global_agents_skills_root,
            self.global_moltbot_skills_root,
        ]
        out: List[Path] = []
        seen = set()
        for root in roots:
            try:
                key = str(root.resolve()).lower()
            except Exception:
                key = str(root).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(root)
        return out

    def _config_candidates(self) -> List[Path]:
        out: List[Path] = []
        env_path = str(os.getenv("OPENCLAW_CONFIG", "")).strip()
        if env_path:
            out.append(Path(env_path).expanduser())
        out.append(Path.home() / ".openclaw" / "openclaw.json")
        out.append(self.workspace_root / ".openclaw" / "openclaw.json")
        seen = set()
        deduped: List[Path] = []
        for path in out:
            try:
                key = str(path.resolve()).lower()
            except Exception:
                key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(path)
        return deduped

    def _load_openclaw_config(self) -> Dict[str, Any]:
        for path in self._config_candidates():
            try:
                if not path.exists() or not path.is_file():
                    continue
                return _load_json_loose(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
        return {}

    @staticmethod
    def _deep_get(container: Any, path: str) -> Any:
        current = container
        for part in str(path or "").split("."):
            key = part.strip()
            if not key:
                continue
            if isinstance(current, dict) and key in current:
                current = current[key]
                continue
            return None
        return current

    def _skill_config_entry(self, name: str, runtime_meta: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        skills_cfg = self._config_data.get("skills") if isinstance(self._config_data, dict) else {}
        if not isinstance(skills_cfg, dict):
            skills_cfg = {}
        entries = skills_cfg.get("entries")
        if not isinstance(entries, dict):
            entries = {}
        skill_key = str(runtime_meta.get("skillKey") or name or "").strip()
        normalized_keys = []
        if skill_key:
            normalized_keys.append(skill_key)
            normalized_keys.append(skill_key.lower())
        if name:
            normalized_keys.append(name)
            normalized_keys.append(name.lower())
        for key in normalized_keys:
            value = entries.get(key)
            if isinstance(value, dict):
                return key, dict(value)
        return skill_key or str(name or "").strip(), {}

    @staticmethod
    def _runtime_env_from_entry(runtime_meta: Dict[str, Any], config_entry: Dict[str, Any]) -> Dict[str, str]:
        env_map: Dict[str, str] = {}
        raw_env = config_entry.get("env")
        if isinstance(raw_env, dict):
            for key, value in raw_env.items():
                if key and str(value).strip():
                    env_map[str(key).strip()] = str(value)
        primary_env = str(runtime_meta.get("primaryEnv") or "").strip()
        requires = runtime_meta.get("requires") if isinstance(runtime_meta, dict) else {}
        if not isinstance(requires, dict):
            requires = {}
        required_envs = OpenClawSkillManager._as_list(requires.get("env"))
        api_key = config_entry.get("apiKey")
        if api_key is None:
            api_key = config_entry.get("api_key")
        if not primary_env and len(required_envs) == 1:
            primary_env = str(required_envs[0] or "").strip()
        if primary_env and isinstance(api_key, str) and api_key.strip():
            env_map.setdefault(primary_env, str(api_key).strip())
        return env_map

    @staticmethod
    def _slugify_name(value: str) -> str:
        raw = str(value or "").strip().lower()
        slug = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("._-")
        return slug or "skill"

    @staticmethod
    def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}, text

        fm_end = -1
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                fm_end = idx
                break
        if fm_end == -1:
            return {}, text

        fm_lines = lines[1:fm_end]
        body = "\n".join(lines[fm_end + 1 :]).strip()
        fm: Dict[str, Any] = {}
        i = 0
        while i < len(fm_lines):
            line = fm_lines[i].rstrip()
            i += 1
            if not line or line.lstrip().startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", line)
            if not m:
                continue
            key = m.group(1).strip()
            value = m.group(2).strip()
            if key == "metadata" and value.startswith("{"):
                raw_json = value
                balance = _json_brace_balance(raw_json)
                while balance > 0 and i < len(fm_lines):
                    nxt = fm_lines[i].rstrip()
                    i += 1
                    raw_json += "\n" + nxt
                    balance = _json_brace_balance(raw_json)
                fm[key] = raw_json
            elif value in {"|", ">"}:
                block_lines: List[str] = []
                while i < len(fm_lines):
                    nxt = fm_lines[i]
                    if not nxt.strip():
                        block_lines.append("")
                        i += 1
                        continue
                    if _leading_spaces(nxt) < 2:
                        break
                    block_lines.append(nxt[2:])
                    i += 1
                fm[key] = "\n".join(block_lines).strip()
            elif not value:
                child, i = _parse_simple_yaml_block(fm_lines, i, 2)
                fm[key] = child
            else:
                fm[key] = _coerce_scalar(value)

        return fm, body

    @staticmethod
    def _as_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
        return [str(value).strip()]

    def _check_eligibility(
        self,
        openclaw_meta: Dict[str, Any],
        *,
        config_entry: Optional[Dict[str, Any]] = None,
        runtime_env: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        config_entry = config_entry if isinstance(config_entry, dict) else {}
        runtime_env = runtime_env if isinstance(runtime_env, dict) else {}

        if config_entry and not _parse_bool(config_entry.get("enabled", True), default=True):
            issues.append("disabled in openclaw config")

        os_list = self._as_list(openclaw_meta.get("os"))
        if os_list:
            normalized = {x.lower() for x in os_list}
            if _current_os_alias() not in normalized and sys.platform.lower() not in normalized:
                issues.append(f"os not supported ({_current_os_alias()})")

        requires = openclaw_meta.get("requires")
        if not isinstance(requires, dict):
            requires = {}

        bins = self._as_list(requires.get("bins"))
        missing_bins = [b for b in bins if shutil.which(b) is None]
        if missing_bins:
            issues.append(f"missing bins: {', '.join(missing_bins)}")

        any_bins = self._as_list(requires.get("anyBins"))
        if any_bins and not any(shutil.which(b) is not None for b in any_bins):
            issues.append(f"none of required bins found: {', '.join(any_bins)}")

        env_vars = self._as_list(requires.get("env"))
        missing_env = [
            k for k in env_vars
            if not str(os.getenv(k, "")).strip() and not str(runtime_env.get(k, "")).strip()
        ]
        if missing_env:
            issues.append(f"missing env: {', '.join(missing_env)}")

        config_paths = self._as_list(requires.get("config"))
        config_bag = config_entry.get("config") if isinstance(config_entry.get("config"), dict) else {}
        missing_config = []
        for path in config_paths:
            value = self._deep_get(config_entry, path)
            if value in (None, "", [], {}):
                value = self._deep_get(config_bag, path)
            if value in (None, "", [], {}):
                missing_config.append(path)
        if missing_config:
            issues.append(f"missing config: {', '.join(missing_config)}")

        return len(issues) == 0, issues

    def _parse_skill(self, skill_file: Path) -> Optional[OpenClawSkill]:
        try:
            raw = skill_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

        frontmatter, body = self._parse_frontmatter(raw)
        metadata_obj: Dict[str, Any] = {}
        raw_metadata = frontmatter.get("metadata")
        if isinstance(raw_metadata, dict):
            metadata_obj = raw_metadata
        elif isinstance(raw_metadata, str) and raw_metadata.strip():
            try:
                parsed = _load_json_loose(raw_metadata)
                if isinstance(parsed, dict):
                    metadata_obj = parsed
            except Exception:
                metadata_obj = {}

        openclaw_meta = metadata_obj.get("openclaw")
        if not isinstance(openclaw_meta, dict):
            openclaw_meta = {}
        clawdbot_meta = metadata_obj.get("clawdbot")
        if not isinstance(clawdbot_meta, dict):
            clawdbot_meta = {}
        runtime_meta = openclaw_meta if openclaw_meta else clawdbot_meta

        name = (
            str(frontmatter.get("name") or "").strip()
            or str(runtime_meta.get("name") or "").strip()
            or skill_file.parent.name
        )
        description = (
            str(frontmatter.get("description") or "").strip()
            or str(runtime_meta.get("description") or "").strip()
            or f"Skill '{name}'"
        )

        skill_key, config_entry = self._skill_config_entry(name, runtime_meta)
        runtime_env = self._runtime_env_from_entry(runtime_meta, config_entry)
        disable_model_invocation = _parse_bool(
            openclaw_meta.get("disableModelInvocation"),
            default=_parse_bool(frontmatter.get("disable_model_invocation"), default=False),
        )
        user_invocable = _parse_bool(
            runtime_meta.get("userInvocable"),
            default=_parse_bool(frontmatter.get("user_invocable"), default=True),
        )
        enabled = _parse_bool(config_entry.get("enabled", True), default=True)
        install_hints = runtime_meta.get("install")
        if not isinstance(install_hints, list):
            install_hints = []
        eligible, issues = self._check_eligibility(
            runtime_meta,
            config_entry=config_entry,
            runtime_env=runtime_env,
        )

        return OpenClawSkill(
            name=name,
            skill_key=str(skill_key or name),
            description=description,
            path=skill_file,
            body=body,
            frontmatter=frontmatter,
            metadata={
                **metadata_obj,
                "_managed_root": str(self.managed_install_root),
                "_managed_roots": [str(root) for root in self._managed_roots()],
            },
            runtime_meta=dict(runtime_meta),
            config_entry=dict(config_entry),
            runtime_env=dict(runtime_env),
            install_hints=list(install_hints),
            eligible=eligible,
            eligibility_issues=issues,
            disable_model_invocation=disable_model_invocation,
            user_invocable=user_invocable,
            enabled=enabled,
        )

    def refresh(self) -> int:
        self._config_data = self._load_openclaw_config()
        collected: Dict[str, OpenClawSkill] = {}
        for root in self._candidate_roots():
            for skill_file in sorted(root.rglob("SKILL.md")):
                skill = self._parse_skill(skill_file)
                if not skill:
                    continue
                key = self._normalize_name(skill.name)
                if not key:
                    continue
                # Later roots override earlier ones (workspace overrides home/env).
                collected[key] = skill
        self._skills_by_key = collected
        return len(self._skills_by_key)

    def list_skills(
        self,
        include_ineligible: bool = False,
        include_disabled: bool = False,
    ) -> List[Dict[str, Any]]:
        skills = sorted(self._skills_by_key.values(), key=lambda s: s.name.lower())
        out: List[Dict[str, Any]] = []
        for skill in skills:
            if not include_ineligible and not skill.eligible:
                continue
            if not include_disabled and (skill.disable_model_invocation or not skill.enabled):
                continue
            out.append(skill.to_summary())
        return out

    def get_skill(self, name: str) -> Optional[OpenClawSkill]:
        key = self._normalize_name(name)
        if not key:
            return None
        return self._skills_by_key.get(key)

    def get_skill_content(self, name: str, max_chars: int = 12000) -> Optional[str]:
        skill = self.get_skill(name)
        if not skill:
            return None
        content = skill.body or ""
        cap = max(500, min(int(max_chars or 12000), 50000))
        if len(content) <= cap:
            return content
        return content[: max(0, cap - 3)] + "..."

    def _safe_extract_zip(self, zip_bytes: bytes, dst_dir: Path) -> None:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            for member in zf.infolist():
                target = dst_dir / member.filename
                resolved = target.resolve()
                if dst_dir not in resolved.parents and resolved != dst_dir:
                    raise ValueError(f"Unsafe zip path: {member.filename}")
            zf.extractall(dst_dir)

    def _is_under_managed_root(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except Exception:
            return False
        for root in self._managed_roots():
            try:
                resolved_root = root.resolve()
                if resolved_root == resolved or resolved_root in resolved.parents:
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _find_npx() -> Optional[str]:
        for candidate in ("npx", "npx.cmd", "npx.exe"):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return None

    def install_from_source(
        self,
        source: str,
        *,
        skill_names: Optional[List[str]] = None,
        agent: str = "codex",
        global_scope: bool = False,
        copy_files: bool = True,
        yes: bool = True,
        timeout_sec: int = 180,
    ) -> Dict[str, Any]:
        raw_source = str(source or "").strip()
        if not raw_source:
            raise ValueError("Skill source is required.")

        npx_bin = self._find_npx()
        if not npx_bin:
            raise ValueError("npx is not available. Install Node.js/npm first.")

        selected_names = []
        for item in skill_names or []:
            name = str(item or "").strip()
            if name:
                selected_names.append(name)

        before_keys = set(self._skills_by_key.keys())
        command = [npx_bin, "skills", "add", raw_source, "--agent", str(agent or "codex").strip() or "codex"]
        for skill_name in selected_names:
            command.extend(["--skill", skill_name])
        if global_scope:
            command.append("--global")
        if copy_files:
            command.append("--copy")
        if yes:
            command.append("--yes")

        env = os.environ.copy()
        env.setdefault("CI", "1")
        env.setdefault("DO_NOT_TRACK", "1")
        env.setdefault("DISABLE_TELEMETRY", "1")

        try:
            completed = subprocess.run(
                command,
                cwd=str(self.workspace_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=max(10, int(timeout_sec or 180)),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"skills install timed out after {exc.timeout} seconds.") from exc
        except Exception as exc:
            raise ValueError(f"Failed to run skills installer: {exc}") from exc

        stdout = str(completed.stdout or "").strip()
        stderr = str(completed.stderr or "").strip()
        if completed.returncode != 0:
            detail = stderr or stdout or f"exit code {completed.returncode}"
            raise ValueError(f"skills install failed: {detail}")

        self.refresh()
        after_keys = set(self._skills_by_key.keys())
        added_keys = sorted(after_keys - before_keys)
        installed = []
        for key in added_keys:
            skill = self._skills_by_key.get(key)
            if not skill:
                continue
            installed.append(
                {
                    "name": skill.name,
                    "skill_key": skill.skill_key,
                    "directory": str(skill.path.parent),
                }
            )

        return {
            "ok": True,
            "installed_count": len(installed),
            "installed": installed,
            "source": raw_source,
            "skill_names": selected_names,
            "agent": str(agent or "codex").strip() or "codex",
            "global_scope": bool(global_scope),
            "copy_files": bool(copy_files),
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
        }

    def install_from_zip_bytes(
        self,
        zip_bytes: bytes,
        filename: str = "skill.zip",
        replace: bool = True,
    ) -> Dict[str, Any]:
        payload = bytes(zip_bytes or b"")
        if not payload:
            raise ValueError("Empty ZIP payload.")
        if len(payload) > 100 * 1024 * 1024:
            raise ValueError("ZIP file is too large (max 100 MB).")

        self.managed_install_root.mkdir(parents=True, exist_ok=True)

        installed: List[Dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="openclaw_skill_install_") as tmp:
            tmp_path = Path(tmp)
            self._safe_extract_zip(payload, tmp_path)

            skill_files = sorted(tmp_path.rglob("SKILL.md"))
            if not skill_files:
                raise ValueError("ZIP does not contain any SKILL.md file.")

            for skill_file in skill_files:
                parsed = self._parse_skill(skill_file)
                if not parsed:
                    continue
                src_dir = skill_file.parent
                suggested_name = parsed.name or src_dir.name
                slug = self._slugify_name(suggested_name)
                dst_dir = self.managed_install_root / slug
                if dst_dir.exists():
                    if not replace:
                        raise ValueError(f"Skill '{slug}' already exists. Enable replace to overwrite.")
                    shutil.rmtree(dst_dir, ignore_errors=True)
                shutil.copytree(src_dir, dst_dir)
                installed.append(
                    {
                        "name": suggested_name,
                        "slug": slug,
                        "directory": str(dst_dir),
                    }
                )

        if not installed:
            raise ValueError("No valid skill folder found in ZIP.")

        self.refresh()
        return {
            "ok": True,
            "installed_count": len(installed),
            "installed": installed,
            "source_filename": str(filename or "skill.zip"),
        }

    def uninstall_skill(self, name: str) -> Dict[str, Any]:
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found.")

        skill_dir = skill.path.parent
        if not self._is_under_managed_root(skill_dir):
            raise ValueError(
                "This skill is not managed by the app install root and cannot be uninstalled here."
            )

        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)
        self.refresh()
        return {
            "ok": True,
            "removed_name": skill.name,
            "removed_directory": str(skill_dir),
        }
