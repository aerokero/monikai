"""
Abstract base class for smart home integrations.
All platform-specific agents (Kasa, Hue, Home Assistant) inherit from this.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Tuple, Optional


class BaseSmartHomeAgent(ABC):
    """
    Abstract interface for smart home device control.
    
    All implementations must support:
    - Device discovery and initialization
    - Power control (on/off)
    - Brightness control (0-100)
    - Color control (by name or HSV tuple)
    - Device state serialization
    """

    def __init__(self, name: str):
        """
        Initialize agent with platform name.
        
        Args:
            name: Platform identifier (e.g., "kasa", "hue", "home_assistant")
        """
        self.platform = name
        self.devices = {}

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize and load known devices from configuration.
        Must be called before any other operations.
        """
        pass

    @abstractmethod
    async def discover_devices(self) -> List[Dict[str, Any]]:
        """
        Discover available devices on the network or remote service.
        
        Returns:
            List of device info dictionaries with structure:
            {
                "platform": str,           # Platform identifier
                "id": str,                 # Unique device ID (IP for Kasa, entity_id for HA, etc)
                "alias": str,              # User-friendly device name
                "model": str,              # Device model
                "type": str,               # Device type (bulb, plug, strip, dimmer, switch, light, etc)
                "is_on": bool,             # Current power state
                "brightness": int|None,    # 0-100 if supported, else None
                "hsv": dict|None,          # {"h": 0-360, "s": 0-100, "v": 0-100} if color capable
                "has_color": bool,         # True if color control supported
                "has_brightness": bool,    # True if brightness control supported
                "has_temperature": bool,   # True if color temperature control supported
                "offline": bool,           # True if device unreachable
            }
        """
        pass

    @abstractmethod
    async def turn_on(self, target: str) -> bool:
        """
        Turn on a device.
        
        Args:
            target: Device identifier (IP, name, entity_id, etc)
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def turn_off(self, target: str) -> bool:
        """
        Turn off a device.
        
        Args:
            target: Device identifier
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def set_brightness(self, target: str, brightness: int) -> bool:
        """
        Set device brightness.
        
        Args:
            target: Device identifier
            brightness: Brightness level (0-100)
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def set_color(self, target: str, color_input: Union[str, Tuple[int, int, int]]) -> bool:
        """
        Set device color.
        
        Args:
            target: Device identifier
            color_input: Either:
                - Color name (string): "red", "blue", "warm", "cool", etc.
                - HSV tuple: (Hue 0-360, Saturation 0-100, Value 0-100)
                - Color temp (for dedicated temp control): "warm", "cool", "daylight"
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def serialize_devices(self) -> List[Dict[str, Any]]:
        """
        Get current device list in standard format.
        
        Returns:
            List of device info dictionaries
        """
        pass

    # ========================================================================
    # Optional helper methods (can be overridden in subclasses)
    # ========================================================================

    def name_to_hsv(self, color_name: str) -> Optional[Tuple[int, int, int]]:
        """
        Convert common color names to HSV tuple.
        Default implementation for consistency across platforms.
        
        Args:
            color_name: Color name (case-insensitive)
            
        Returns:
            (Hue 0-360, Saturation 0-100, Value 0-100) or None if not found
        """
        color_name = color_name.lower().strip()
        colors = {
            # Primary colors
            "red": (0, 100, 100),
            "orange": (30, 100, 100),
            "yellow": (60, 100, 100),
            "green": (120, 100, 100),
            "cyan": (180, 100, 100),
            "blue": (240, 100, 100),
            "purple": (300, 100, 100),
            "pink": (330, 100, 100),
            # White variations
            "white": (0, 0, 100),
            "warm": (30, 20, 100),      # Warm white (approx 2700K)
            "cool": (200, 10, 100),     # Cool white (approx 4000K)
            "daylight": (200, 5, 100),  # Daylight (approx 5000K)
            "neutral": (0, 0, 100),     # Neutral white
            # Aliases
            "warm_white": (30, 20, 100),
            "cool_white": (200, 10, 100),
        }
        return colors.get(color_name, None)

    async def resolve_device_by_name(self, name: str) -> Optional[str]:
        """
        Find device ID by name (case-insensitive).
        Override in subclass if needed for custom resolution logic.
        
        Args:
            name: Device name to search for
            
        Returns:
            Device ID if found, None otherwise
        """
        name_lower = name.lower()
        for device_id, device_info in self.devices.items():
            if isinstance(device_info, dict):
                alias = device_info.get("alias", "").lower()
            else:
                alias = getattr(device_info, "alias", "").lower()
            
            if alias == name_lower:
                return device_id
        return None
