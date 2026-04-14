"""
Home Assistant Integration Agent.
Communicates with Home Assistant via REST API.
"""

import asyncio
import aiohttp
from typing import List, Dict, Any, Optional, Tuple, Union
import json
from .base_agent import BaseSmartHomeAgent


class HomeAssistantAgent(BaseSmartHomeAgent):
    """
    Home Assistant integration for comprehensive smart home control.
    
    Requires:
    - url: Home Assistant instance URL (e.g., "http://192.168.1.100:8123")
    - token: Long-lived access token from HA
    
    Supports:
    - Entity discovery and filtering (light, switch, sensor, etc.)
    - Light control (on/off, brightness, color_temp)
    - Switch control (on/off)
    - Optional WebSocket for state streaming
    """

    def __init__(self, ha_url: Optional[str] = None, ha_token: Optional[str] = None,
                 entities_filter: Optional[List[str]] = None):
        super().__init__(name="home_assistant")
        self.ha_url = ha_url.rstrip("/") if ha_url else None
        self.ha_token = ha_token
        self.entities_filter = entities_filter or ["light.*", "switch.*"]
        self.session = None
        self.entities = {}  # Maps entity_id -> entity_state
        self._initialized = False

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session is available."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def _entity_matches_filter(self, entity_id: str) -> bool:
        """Check if entity matches any filter pattern."""
        entity_id = str(entity_id or "").lower()
        
        for pattern in self.entities_filter:
            pattern = pattern.lower()
            if pattern.endswith(".*"):
                domain = pattern[:-2]  # Remove .*
                if entity_id.startswith(f"{domain}."):
                    return True
            elif entity_id == pattern:
                return True
        
        return False

    async def _get(self, endpoint: str) -> Optional[Dict]:
        """Make GET request to Home Assistant."""
        if not self.ha_url or not self.ha_token:
            return None
        
        try:
            session = await self._ensure_session()
            url = f"{self.ha_url}/api{endpoint}"
            headers = {
                "Authorization": f"Bearer {self.ha_token}",
                "Content-Type": "application/json"
            }
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 401:
                    print("[HA Agent] 401 Unauthorized - Invalid token?")
                else:
                    print(f"[HA Agent] GET {endpoint}: HTTP {resp.status}")
        except asyncio.TimeoutError:
            print(f"[HA Agent] GET {endpoint}: Timeout connecting to {self.ha_url}")
        except Exception as e:
            print(f"[HA Agent] GET {endpoint}: {e}")
        return None

    async def _post(self, endpoint: str, data: Dict) -> bool:
        """Make POST request to Home Assistant."""
        if not self.ha_url or not self.ha_token:
            return False
        
        try:
            session = await self._ensure_session()
            url = f"{self.ha_url}/api{endpoint}"
            headers = {
                "Authorization": f"Bearer {self.ha_token}",
                "Content-Type": "application/json"
            }
            async with session.post(url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status in (200, 201):
                    return True
                else:
                    print(f"[HA Agent] POST {endpoint}: HTTP {resp.status}")
        except asyncio.TimeoutError:
            print(f"[HA Agent] POST {endpoint}: Timeout")
        except Exception as e:
            print(f"[HA Agent] POST {endpoint}: {e}")
        return False

    async def initialize(self) -> None:
        """Initialize Home Assistant Agent - fetch all entities."""
        if not self.ha_url or not self.ha_token:
            print("[HA Agent] No ha_url or ha_token configured, skipping initialization.")
            self._initialized = False
            return
        
        print(f"[HA Agent] Initializing with instance {self.ha_url}...")
        states_data = await self._get("/states")
        
        if states_data is None:
            print("[HA Agent] Failed to connect to Home Assistant")
            self._initialized = False
            return
        
        # Process entities
        if isinstance(states_data, list):
            for entity in states_data:
                entity_id = entity.get("entity_id", "")
                if self._entity_matches_filter(entity_id):
                    self.entities[entity_id] = entity
        
        print(f"[HA Agent] Initialized with {len(self.entities)} entities")
        self._initialized = True

    async def discover_devices(self) -> List[Dict[str, Any]]:
        """Discover controllable entities in Home Assistant."""
        await self.initialize()
        return self.serialize_devices()

    async def turn_on(self, target: str) -> bool:
        """Turn on an entity (light or switch)."""
        entity_id = await self._resolve_entity_id(target)
        if not entity_id:
            print(f"[HA Agent] Entity not found: {target}")
            return False
        
        domain = entity_id.split(".")[0]
        service = f"{domain}/turn_on" if domain in ("light", "switch") else None
        
        if not service:
            print(f"[HA Agent] Cannot control domain '{domain}' with turn_on")
            return False
        
        success = await self._post(f"/services/{service}", {"entity_id": entity_id})
        if success:
            if entity_id in self.entities:
                self.entities[entity_id]["state"] = "on"
            print(f"[HA Agent] Turned on: {target}")
        return success

    async def turn_off(self, target: str) -> bool:
        """Turn off an entity (light or switch)."""
        entity_id = await self._resolve_entity_id(target)
        if not entity_id:
            print(f"[HA Agent] Entity not found: {target}")
            return False
        
        domain = entity_id.split(".")[0]
        service = f"{domain}/turn_off" if domain in ("light", "switch") else None
        
        if not service:
            print(f"[HA Agent] Cannot control domain '{domain}' with turn_off")
            return False
        
        success = await self._post(f"/services/{service}", {"entity_id": entity_id})
        if success:
            if entity_id in self.entities:
                self.entities[entity_id]["state"] = "off"
            print(f"[HA Agent] Turned off: {target}")
        return success

    async def set_brightness(self, target: str, brightness: int) -> bool:
        """Set brightness for a light (0-100)."""
        entity_id = await self._resolve_entity_id(target)
        if not entity_id:
            print(f"[HA Agent] Entity not found: {target}")
            return False
        
        domain = entity_id.split(".")[0]
        if domain != "light":
            print(f"[HA Agent] Only light entities support brightness")
            return False
        
        # HA uses 0-255 for brightness
        ha_brightness = max(1, int((brightness / 100.0) * 255))
        
        success = await self._post("/services/light/turn_on", {
            "entity_id": entity_id,
            "brightness": ha_brightness
        })
        
        if success:
            print(f"[HA Agent] Set brightness to {brightness}%: {target}")
        return success

    async def set_color(self, target: str, color_input: Union[str, Tuple[int, int, int]]) -> bool:
        """Set color for a light."""
        entity_id = await self._resolve_entity_id(target)
        if not entity_id:
            print(f"[HA Agent] Entity not found: {target}")
            return False
        
        domain = entity_id.split(".")[0]
        if domain != "light":
            print(f"[HA Agent] Only light entities support color control")
            return False
        
        # Get HSV tuple
        hsv = None
        call_data = {"entity_id": entity_id}
        
        if isinstance(color_input, str):
            # Try HSV first
            hsv = self.name_to_hsv(color_input)
            if hsv:
                h, s, v = hsv
                # Convert to RGB for Home Assistant (HA prefers RGB)
                rgb = self._hsv_to_rgb(h, s, v)
                call_data["rgb_color"] = rgb
            else:
                # Try color temp string
                mirek = self._color_temp_to_mirek(color_input)
                if mirek:
                    call_data["color_temp_kelvin"] = self._mirek_to_kelvin(mirek)
                else:
                    print(f"[HA Agent] Unknown color: {color_input}")
                    return False
        elif isinstance(color_input, (tuple, list)) and len(color_input) == 3:
            h, s, v = color_input
            rgb = self._hsv_to_rgb(h, s, v)
            call_data["rgb_color"] = rgb
        else:
            return False
        
        success = await self._post("/services/light/turn_on", call_data)
        if success:
            print(f"[HA Agent] Set color: {target}")
        return success

    def _hsv_to_rgb(self, h: float, s: float, v: float) -> Tuple[int, int, int]:
        """Convert HSV (0-360, 0-100, 0-100) to RGB (0-255, 0-255, 0-255)."""
        h = h % 360.0
        s = s / 100.0
        v = v / 100.0
        
        c = v * s
        x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
        m = v - c
        
        if 0 <= h < 60:
            r, g, b = c, x, 0
        elif 60 <= h < 120:
            r, g, b = x, c, 0
        elif 120 <= h < 180:
            r, g, b = 0, c, x
        elif 180 <= h < 240:
            r, g, b = 0, x, c
        elif 240 <= h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        
        return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))

    def _color_temp_to_mirek(self, color_name: str) -> Optional[int]:
        """Map color temperature names to mirek values."""
        mirek_map = {
            "warm": 500,
            "warm_white": 500,
            "neutral": 370,
            "cool": 250,
            "cool_white": 250,
            "daylight": 200,
        }
        return mirek_map.get(color_name.lower())

    def _mirek_to_kelvin(self, mirek: int) -> int:
        """Convert mirek to Kelvin (K = 1000000 / mirek)."""
        if mirek <= 0:
            return 6500
        return max(2000, min(6500, int(1000000 / mirek)))

    async def _resolve_entity_id(self, target: str) -> Optional[str]:
        """Resolve target name/id to entity_id."""
        target = str(target or "").strip().lower()
        
        # Direct ID match
        if target in self.entities:
            return target
        
        # Friendly name match
        for entity_id, entity_state in self.entities.items():
            friendly_name = entity_state.get("attributes", {}).get("friendly_name", "").lower()
            if friendly_name == target:
                return entity_id
        
        return None

    def serialize_devices(self) -> List[Dict[str, Any]]:
        """Serialize all HA entities to standard format."""
        devices = []
        
        for entity_id, entity_state in self.entities.items():
            domain = entity_id.split(".")[0]
            state = entity_state.get("state", "unknown")
            attrs = entity_state.get("attributes", {})
            
            # Determine device capabilities
            has_brightness = "brightness" in attrs
            has_color = any(k in attrs for k in ["rgb_color", "xy_color", "hs_color"])
            has_temperature = "color_temp_kelvin" in attrs or "color_temp" in attrs
            
            # Build base device info
            device = {
                "platform": "home_assistant",
                "id": entity_id,
                "alias": attrs.get("friendly_name", entity_id),
                "model": attrs.get("device_name", domain),
                "type": domain,  # light, switch, sensor, etc.
                "is_on": state.lower() in ("on", "true", "1"),
                "brightness": None,
                "hsv": None,
                "has_color": has_color,
                "has_brightness": has_brightness,
                "has_temperature": has_temperature,
                "offline": state.lower() in ("unavailable", "unknown"),
            }
            
            # Add brightness if available
            if has_brightness and isinstance(attrs.get("brightness"), (int, float)):
                brightness = int((attrs.get("brightness", 0) / 255.0) * 100)
                device["brightness"] = min(100, max(0, brightness))
            
            # Add HSV if color capable
            if has_color and "hs_color" in attrs:
                h, s = attrs["hs_color"]
                v = device.get("brightness", 100)
                device["hsv"] = {"h": int(h), "s": int(s), "v": v}
            elif has_color and "rgb_color" in attrs:
                r, g, b = attrs["rgb_color"]
                h, s, v = self._rgb_to_hsv(r, g, b)
                device["hsv"] = {"h": int(h), "s": int(s), "v": int(v)}
            
            devices.append(device)
        
        return devices

    def _rgb_to_hsv(self, r: int, g: int, b: int) -> Tuple[float, float, float]:
        """Convert RGB (0-255) to HSV (0-360, 0-100, 0-100)."""
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        dc = max_c - min_c
        
        # Calculate Hue
        if dc == 0:
            h = 0
        elif max_c == r:
            h = 60 * (((g - b) / dc) % 6)
        elif max_c == g:
            h = 60 * ((b - r) / dc + 2)
        else:  # max_c == b
            h = 60 * ((r - g) / dc + 4)
        
        # Calculate Saturation and Value
        s = 0 if max_c == 0 else (dc / max_c) * 100
        v = max_c * 100
        
        return (h % 360, s, v)

    async def close(self):
        """Clean up aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def __del__(self):
        """Ensure session is closed on deletion."""
        if self.session and not self.session.closed:
            try:
                asyncio.create_task(self.close())
            except:
                pass
