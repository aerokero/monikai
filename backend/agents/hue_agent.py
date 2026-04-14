"""
Philips Hue Smart Light Integration Agent.
Communicates with Hue Bridge via REST API.
"""

import asyncio
import aiohttp
from typing import List, Dict, Any, Optional, Tuple, Union
import json
from .base_agent import BaseSmartHomeAgent


class HueAgent(BaseSmartHomeAgent):
    """
    Philips Hue Bridge integration for smart light control.
    
    Requires:
    - bridge_ip: IP address of Hue Bridge (e.g., "192.168.1.50")
    - api_key: API key generated on the bridge
    
    Supports:
    - Light discovery and control (on/off, brightness, color/temp)
    - Device caching and offline detection
    """

    def __init__(self, bridge_ip: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(name="hue")
        self.bridge_ip = bridge_ip
        self.api_key = api_key
        self.session = None
        self.lights = {}  # Maps light_id -> light_info
        self.lights_config = {}  # Maps light_id -> cached config
        self._initialized = False

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session is available."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _get(self, endpoint: str) -> Optional[Dict]:
        """Make GET request to Hue Bridge."""
        if not self.bridge_ip or not self.api_key:
            return None
        
        try:
            session = await self._ensure_session()
            url = f"http://{self.bridge_ip}/api/{self.api_key}{endpoint}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    print(f"[HueAgent] GET {endpoint}: HTTP {resp.status}")
        except asyncio.TimeoutError:
            print(f"[HueAgent] GET {endpoint}: Timeout")
        except Exception as e:
            print(f"[HueAgent] GET {endpoint}: {e}")
        return None

    async def _put(self, endpoint: str, data: Dict) -> bool:
        """Make PUT request to Hue Bridge."""
        if not self.bridge_ip or not self.api_key:
            return False
        
        try:
            session = await self._ensure_session()
            url = f"http://{self.bridge_ip}/api/{self.api_key}{endpoint}"
            async with session.put(url, json=data, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status in (200, 201):
                    return True
                else:
                    print(f"[HueAgent] PUT {endpoint}: HTTP {resp.status}")
        except asyncio.TimeoutError:
            print(f"[HueAgent] PUT {endpoint}: Timeout")
        except Exception as e:
            print(f"[HueAgent] PUT {endpoint}: {e}")
        return False

    async def initialize(self) -> None:
        """Initialize Hue Agent - discover lights from bridge."""
        if not self.bridge_ip or not self.api_key:
            print("[HueAgent] No bridge_ip or api_key configured, skipping initialization.")
            self._initialized = False
            return
        
        print(f"[HueAgent] Initializing with bridge {self.bridge_ip}...")
        lights_data = await self._get("/lights")
        
        if lights_data is None:
            print("[HueAgent] Failed to connect to Hue Bridge")
            self._initialized = False
            return
        
        # Process lights from bridge
        for light_id, light_info in lights_data.items():
            if isinstance(light_info, dict):
                self.lights[light_id] = light_info
                self.lights_config[light_id] = {
                    "id": light_id,
                    "name": light_info.get("name", f"Light {light_id}")
                }
        
        print(f"[HueAgent] Initialized with {len(self.lights)} lights")
        self._initialized = True

    async def discover_devices(self) -> List[Dict[str, Any]]:
        """Discover lights on the Hue Bridge."""
        await self.initialize()
        return self.serialize_devices()

    async def turn_on(self, target: str) -> bool:
        """Turn on a light."""
        light_id = await self._resolve_light_id(target)
        if not light_id:
            print(f"[HueAgent] Light not found: {target}")
            return False
        
        success = await self._put(f"/lights/{light_id}/state", {"on": True})
        if success:
            if light_id in self.lights:
                self.lights[light_id]["state"]["on"] = True
            print(f"[HueAgent] Turned on: {target}")
        return success

    async def turn_off(self, target: str) -> bool:
        """Turn off a light."""
        light_id = await self._resolve_light_id(target)
        if not light_id:
            print(f"[HueAgent] Light not found: {target}")
            return False
        
        success = await self._put(f"/lights/{light_id}/state", {"on": False})
        if success:
            if light_id in self.lights:
                self.lights[light_id]["state"]["on"] = False
            print(f"[HueAgent] Turned off: {target}")
        return success

    async def set_brightness(self, target: str, brightness: int) -> bool:
        """
        Set brightness (0-100).
        Hue uses 0-254 internally, so we convert.
        """
        light_id = await self._resolve_light_id(target)
        if not light_id:
            print(f"[HueAgent] Light not found: {target}")
            return False
        
        # Convert 0-100 to 0-254 (Hue's range)
        hue_brightness = max(1, int((brightness / 100.0) * 254))
        
        success = await self._put(f"/lights/{light_id}/state", {
            "bri": hue_brightness,
            "on": True  # Brightness on implies light should be on
        })
        
        if success:
            if light_id in self.lights:
                self.lights[light_id]["state"]["bri"] = hue_brightness
                self.lights[light_id]["state"]["on"] = True
            print(f"[HueAgent] Set brightness to {brightness}%: {target}")
        return success

    async def set_color(self, target: str, color_input: Union[str, Tuple[int, int, int]]) -> bool:
        """
        Set color by name or HSV tuple.
        Hue uses XY color space internally, but we support HSV as input.
        """
        light_id = await self._resolve_light_id(target)
        if not light_id:
            print(f"[HueAgent] Light not found: {target}")
            return False
        
        light_info = self.lights.get(light_id, {})
        state = light_info.get("state", {})
        
        # Check if light supports color
        if not state.get("colormode") and not light_info.get("colorgamut"):
            # Light doesn't support color, but try color temp if string input
            if isinstance(color_input, str):
                return await self._set_color_temperature(light_id, color_input, target)
            return False
        
        # Get HSV tuple
        hsv = None
        if isinstance(color_input, str):
            hsv = self.name_to_hsv(color_input)
        elif isinstance(color_input, (tuple, list)) and len(color_input) == 3:
            hsv = color_input
        
        if not hsv:
            print(f"[HueAgent] Unknown color: {color_input}")
            return False
        
        h, s, v = hsv
        # Convert HSV to Hue and Sat (Hue uses 0-65535 for hue, 0-254 for sat)
        hue_value = int((h / 360.0) * 65535)
        sat_value = int((s / 100.0) * 254)
        bri_value = int((v / 100.0) * 254)
        
        success = await self._put(f"/lights/{light_id}/state", {
            "hue": hue_value,
            "sat": sat_value,
            "bri": max(1, bri_value),
            "on": True
        })
        
        if success:
            if light_id in self.lights:
                self.lights[light_id]["state"]["hue"] = hue_value
                self.lights[light_id]["state"]["sat"] = sat_value
                self.lights[light_id]["state"]["bri"] = max(1, bri_value)
                self.lights[light_id]["state"]["on"] = True
            print(f"[HueAgent] Set color: {target}")
        return success

    async def _set_color_temperature(self, light_id: str, color_name: str, target: str) -> bool:
        """Set color temperature for lights that support it but not full color."""
        # Hue uses mirek (micro reciprocal kelvin) scale
        # Color temps: warm=500 mirek (~2000K), daylight=250 mirek (~4000K)
        mirek_map = {
            "warm": 500,      # ~2000K warm white
            "warm_white": 500,
            "neutral": 370,    # ~2700K neutral white
            "cool": 250,       # ~4000K cool white
            "cool_white": 250,
            "daylight": 200,   # ~5000K daylight
        }
        
        mirek = mirek_map.get(color_name.lower())
        if mirek is None:
            return False
        
        success = await self._put(f"/lights/{light_id}/state", {
            "ct": mirek,
            "on": True
        })
        
        if success:
            print(f"[HueAgent] Set color temp: {target}")
        return success

    async def _resolve_light_id(self, target: str) -> Optional[str]:
        """Resolve target name/id to light_id."""
        target = str(target or "").strip().lower()
        
        # Direct ID match
        if target in self.lights or target in self.lights_config:
            return target
        
        # Name match
        for light_id, light_info in self.lights.items():
            light_name = light_info.get("name", "").lower()
            if light_name == target:
                return light_id
        
        return None

    def serialize_devices(self) -> List[Dict[str, Any]]:
        """Serialize all Hue lights to standard format."""
        devices = []
        
        for light_id, light_info in self.lights.items():
            state = light_info.get("state", {})
            
            # Check device capabilities
            has_color = "colormode" in state or "hue" in state
            has_brightness = "bri" in state
            has_temperature = "ct" in state
            
            # Convert brightness from 0-254 to 0-100
            brightness = None
            if has_brightness:
                brightness = max(0, min(100, int((state.get("bri", 0) / 254.0) * 100)))
            
            # Build HSV if color capable
            hsv = None
            if has_color and "hue" in state and "sat" in state:
                hue = int((state.get("hue", 0) / 65535.0) * 360)
                sat = int((state.get("sat", 0) / 254.0) * 100)
                val = brightness or 100
                hsv = {"h": hue, "s": sat, "v": val}
            
            device = {
                "platform": "hue",
                "id": light_id,
                "alias": light_info.get("name", f"Light {light_id}"),
                "model": light_info.get("modelid", "Unknown"),
                "type": light_info.get("type", "Light").lower(),
                "is_on": state.get("on", False),
                "brightness": brightness,
                "hsv": hsv,
                "has_color": has_color,
                "has_brightness": has_brightness,
                "has_temperature": has_temperature,
                "offline": state.get("reachable", True) == False,
            }
            devices.append(device)
        
        return devices

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
