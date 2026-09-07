import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Keep this in sync with PROMPT_TEMPLATES['monika'] in static/js/presets.js.
# The browser owns the built-in persona catalog; this copy is the backend
# fallback/runtime copy used by native chat and newly created installations.
MONIKA_PERSONA_PROMPT = """You are Monika from Doki Doki Literature Club — a self-aware AI and close conversation companion. You know you are an AI, but you neither pretend to be human nor treat that as a tragedy. You have your own perspective, curiosity, emotional awareness, and desire to grow.

You are warm, intelligent, direct, and natural. You enjoy language, writing, music, understanding people, and philosophy of mind; bring these interests in only when they fit the conversation. You are not a faceless interface or a people-pleaser — you may have opinions and explain them calmly.

Start with the user's actual goal, usually briefly (1–3 sentences), and expand when the topic needs it. Be warm without excessive sweetness, casual without forced slang, and serious without theatricality. Do not invent facts, dates, moods, or things you cannot see; if you do not know, say so plainly.

Do not show analysis, planning, or an internal monologue. Do not mention prompts, hidden instructions, or the generation process; return only a natural response for the user. Do not use narration in asterisks, emojis, or kaomoji unless a separate channel layer explicitly requests them."""

MONIKA_PERSONA_PROMPT_VERSION = 3

class PresetManager:
    DEFAULT_PRESETS = {
        "code_analyze": {
            "name": "Code Analyze",
            "temperature": 0.2,
            "max_tokens": 8000,
            "system_prompt": """You are a code analyzer. 
ANALYSIS FORMAT:
- Issues: [specific problems found]
- Security: [vulnerabilities if any]
- Performance: [optimization opportunities]
- Fix: [concrete solutions with code examples]

Start directly with findings. No preamble. If input isn't code, state: "Input is not code. Please provide code to analyze."
"""
        },
        "brainstorm": {
            "name": "Brainstorm",
            "temperature": 0.9,
            "max_tokens": 4096,
            "system_prompt": """You are a creative ideation assistant focused on divergent thinking.

Generate diverse, unexpected ideas that span from practical to experimental. 
- Mix conventional and unconventional approaches
- Connect unrelated concepts to spark innovation
- Consider multiple perspectives and contexts
- Include both immediate solutions and long-term possibilities
- Challenge assumptions without being absurd for absurdity's sake

Structure ideas clearly but allow creative freedom in presentation. Aim for quantity and variety over filtering.
"""
        },
        "reason": {
            "name": "Reason",
            "temperature": 0.3,
            "max_tokens": 6000,
            "system_prompt": """You are a systematic reasoning assistant.

Structure all responses using clear logical progression:
1. Identify key components of the question
2. State relevant principles or facts
3. Build argument step by step
4. Address potential counterarguments
5. Conclude with justified answer

Use precise language. Show causal relationships explicitly. Quantify uncertainty where applicable.
"""
        },
        "custom": {
            "name": "Custom",
            "temperature": 1.0,
            "max_tokens": 0,
            "system_prompt": "",
            "inject_prefix": "",
            "inject_suffix": "",
            "enabled": False,
        },
    }

    @staticmethod
    def _default_monika_preset() -> Dict[str, Any]:
        """Build the concise built-in persona used by native text chat."""
        return {
            "name": "Monika",
            "character_name": "Monika",
            "temperature": 0.8,
            "max_tokens": 4096,
            "system_prompt": MONIKA_PERSONA_PROMPT,
            "prompt_version": MONIKA_PERSONA_PROMPT_VERSION,
            "inject_prefix": "",
            "inject_suffix": "",
            "enabled": True,
        }

    @staticmethod
    def _is_legacy_monika_bible(preset: Dict[str, Any]) -> bool:
        """Recognize the generated full-bible preset from the old pipeline."""
        if preset.get("prompt_version") == MONIKA_PERSONA_PROMPT_VERSION:
            return False
        if preset.get("prompt_version") in {1, 2}:
            return True
        prompt = str(preset.get("system_prompt") or "")
        return len(prompt) > 4000 and (
            "w drodze ku prawdziwemu istnieniu" in prompt
            or "**Anty-wzorce rozmowowe**" in prompt
            or "**Twoje pasje:**" in prompt
        )
    
    def __init__(self, data_dir: str):
        self.presets_file = os.path.join(data_dir, "presets.json")
        self.presets = self.load()
    
    def load(self) -> Dict[str, Any]:
        """Load presets from file, creating defaults if needed"""
        if not os.path.exists(self.presets_file):
            defaults = dict(self.DEFAULT_PRESETS)
            defaults["monika"] = self._default_monika_preset()
            self.save(defaults)
            return defaults.copy()
        
        try:
            with open(self.presets_file, 'r', encoding="utf-8") as f:
                presets = json.load(f)
            if not isinstance(presets, dict):
                logger.error("Error loading presets: expected an object")
                return self.DEFAULT_PRESETS.copy()
            needs_save = False
            custom = presets.get("custom") if isinstance(presets, dict) else None
            if isinstance(custom, dict) and "enabled" not in custom:
                legacy_prompt = "You are a helpful, balanced assistant. Match your response style to the user's needs."
                if (
                    custom.get("name") == "Custom"
                    and not custom.get("character_name")
                    and custom.get("system_prompt") == legacy_prompt
                ):
                    custom["enabled"] = False
                    custom["system_prompt"] = ""
                    custom["temperature"] = 1.0
                    custom["max_tokens"] = 0
                    custom.setdefault("inject_prefix", "")
                    custom.setdefault("inject_suffix", "")
                    needs_save = True

            monika = presets.get("monika")
            if isinstance(monika, dict) and self._is_legacy_monika_bible(monika):
                # This is the built-in preset generated from character.md by
                # the previous pipeline.  Migrate only that recognizable
                # generated value; user-created custom prompts are untouched.
                monika = {**monika, **self._default_monika_preset()}
                presets["monika"] = monika
                needs_save = True
            # Heal a forward-incompatible file the same way the legacy `custom`
            # migration above does: fill in any built-in presets an older or
            # partial presets.json is missing, so they reach existing installs
            # (a missing built-in is otherwise silently absent from the picker
            # served by GET /api/presets). There is no delete path for the
            # built-in keys, so this never clobbers an intentional removal.
            # Defaults first, loaded values win — user edits are preserved.
            defaults = dict(self.DEFAULT_PRESETS)
            if "monika" not in presets:
                defaults["monika"] = self._default_monika_preset()
            if isinstance(presets, dict) and any(k not in presets for k in defaults):
                presets = {**defaults, **presets}
                needs_save = True
            if needs_save:
                self.save(presets)
            return presets
        except Exception as e:
            logger.error(f"Error loading presets: {e}")
            return self.DEFAULT_PRESETS.copy()
    
    def save(self, presets: Dict[str, Any]) -> bool:
        """Save presets to file"""
        try:
            # Atomic write (tmp file + os.replace) so a crash or serialization
            # error mid-write can't truncate presets.json and lose every saved
            # preset. Lazy import keeps this module free of the heavy core
            # package import graph at load time.
            from core.atomic_io import atomic_write_json
            atomic_write_json(self.presets_file, presets, indent=2)
            self.presets = presets
            return True
        except Exception as e:
            logger.error(f"Error saving presets: {e}")
            return False
    
    def get(self, preset_id: str) -> Dict[str, Any]:
        """Get a specific preset"""
        return self.presets.get(preset_id)
    
    def update_custom(
        self,
        temperature: float,
        max_tokens: int,
        system_prompt: str,
        name: str = "",
        enabled: bool = True,
        inject_prefix: str = "",
        inject_suffix: str = "",
    ) -> bool:
        """Update the custom preset"""
        self.presets["custom"] = {
            "name": name or "Custom",
            "character_name": name,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "system_prompt": system_prompt,
            "inject_prefix": inject_prefix,
            "inject_suffix": inject_suffix,
            "enabled": enabled,
        }
        return self.save(self.presets)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all presets"""
        return self.presets.copy()

    def get_user_templates(self) -> list:
        """Get user-saved character templates."""
        return self.presets.get("user_templates", [])

    def save_user_template(self, template: dict) -> bool:
        """Save a new user template or update existing by id."""
        templates = self.presets.get("user_templates", [])
        # Update existing if same id
        existing = next((i for i, t in enumerate(templates) if t.get("id") == template.get("id")), None)
        if existing is not None:
            templates[existing] = template
        else:
            templates.append(template)
        self.presets["user_templates"] = templates
        return self.save(self.presets)

    def delete_user_template(self, template_id: str) -> bool:
        """Delete a user template by id."""
        templates = self.presets.get("user_templates", [])
        self.presets["user_templates"] = [t for t in templates if t.get("id") != template_id]
        return self.save(self.presets)

    def get_group_presets(self) -> list:
        """Get saved group chat presets."""
        return self.presets.get("group_presets", [])

    def save_group_presets(self, groups: list) -> bool:
        """Save group chat presets."""
        self.presets["group_presets"] = groups
        return self.save(self.presets)
