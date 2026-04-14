import asyncio
from kasa import Discover
from .base_agent import BaseSmartHomeAgent


class KasaAgent(BaseSmartHomeAgent):
    def __init__(self, known_devices=None):
        super().__init__(name="kasa")
        self.known_devices_config = [d for d in (known_devices or []) if isinstance(d, dict) and d.get("ip")]
        self._known_devices_by_ip = {str(d["ip"]): dict(d) for d in self.known_devices_config}

    def _is_offline_stub(self, dev):
        return isinstance(dev, dict) and dev.get("_stub") == "offline"

    def _set_offline_stub(self, ip, alias=None, info=None):
        existing = self.devices.get(ip)
        base = {}
        if isinstance(info, dict):
            base.update(info)
        if self._is_offline_stub(existing):
            base = {**existing, **base}
        self.devices[ip] = {
            "_stub": "offline",
            "ip": ip,
            "alias": alias or base.get("alias") or ip,
            "model": base.get("model") or "Unknown",
            "type": base.get("type") or "unknown",
            "is_on": False,
            "brightness": base.get("brightness"),
            "hsv": base.get("hsv"),
            "has_color": bool(base.get("has_color", False)),
            "has_brightness": bool(base.get("has_brightness", False)),
            "offline": True,
        }

    def _device_to_info(self, ip, dev):
        if self._is_offline_stub(dev):
            return {
                "ip": ip,
                "alias": dev.get("alias") or ip,
                "model": dev.get("model") or "Unknown",
                "type": dev.get("type") or "unknown",
                "is_on": False,
                "brightness": dev.get("brightness"),
                "hsv": dev.get("hsv"),
                "has_color": bool(dev.get("has_color", False)),
                "has_brightness": bool(dev.get("has_brightness", False)),
                "offline": True,
            }

        dev_type = "unknown"
        if dev.is_bulb:
            dev_type = "bulb"
        elif dev.is_plug:
            dev_type = "plug"
        elif dev.is_strip:
            dev_type = "strip"
        elif dev.is_dimmer:
            dev_type = "dimmer"

        return {
            "ip": ip,
            "alias": dev.alias,
            "model": dev.model,
            "type": dev_type,
            "is_on": dev.is_on,
            "brightness": dev.brightness if dev.is_bulb or dev.is_dimmer else None,
            "hsv": dev.hsv if dev.is_bulb and dev.is_color else None,
            "has_color": dev.is_color if dev.is_bulb else False,
            "has_brightness": dev.is_dimmable if dev.is_bulb or dev.is_dimmer else False,
            "offline": False,
        }

    def serialize_devices(self):
        device_list = []
        for ip, dev in self.devices.items():
            try:
                device_list.append(self._device_to_info(ip, dev))
            except Exception:
                continue
        return device_list

    def _resolve_target_ip(self, target):
        target = str(target or "").strip()
        if not target:
            return None
        if target in self.devices:
            return target
        for ip, dev in self.devices.items():
            alias = dev.get("alias") if isinstance(dev, dict) else getattr(dev, "alias", None)
            if alias and str(alias).lower() == target.lower():
                return ip
        if target.count(".") == 3:
            return target
        return None

    async def _discover_target(self, target):
        ip = self._resolve_target_ip(target)
        if not ip:
            return None
        try:
            dev = await Discover.discover_single(ip)
            if dev:
                await dev.update()
                self.devices[ip] = dev
                return dev
        except Exception:
            pass
        return None

    async def initialize(self):
        """Initializes devices from the saved configuration."""
        if self.known_devices_config:
            print(f"[KasaAgent] Initializing {len(self.known_devices_config)} known devices...")
            tasks = []
            for d in self.known_devices_config:
                if not d: continue
                ip = d.get('ip')
                alias = d.get('alias')
                if ip:
                    # Create a device instance from IP
                    tasks.append(self._add_known_device(ip, alias, d))
            
            if tasks:
                await asyncio.gather(*tasks)

    async def _add_known_device(self, ip, alias, info):
        """Adds a device from settings without discovery scan."""
        try:
            dev = await Discover.discover_single(ip)
            if dev:
                await dev.update()
                self.devices[ip] = dev
                print(f"[KasaAgent] Loaded known device: {dev.alias} ({ip})")
            else:
                 print(f"[KasaAgent] Could not connect to known device at {ip}")
                 self._set_offline_stub(ip, alias=alias, info=info)
        except Exception as e:
            print(f"[KasaAgent] Error loading known device {ip}: {e}")
            self._set_offline_stub(ip, alias=alias, info=info)

    async def discover_devices(self):
        """Discovers devices on the local network."""
        print("Discovering Kasa devices (Broadcast)...")
        # Use explicit broadcast and slightly longer timeout for Windows reliability
        found_devices = await Discover.discover(target="255.255.255.255", timeout=5)
        print(f"[KasaAgent] Raw discovery found {len(found_devices)} devices.")

        for ip, dev in found_devices.items():
            await dev.update()
            self.devices[ip] = dev

        for ip, info in self._known_devices_by_ip.items():
            if ip not in found_devices:
                self._set_offline_stub(ip, alias=info.get("alias"), info=info)

        device_list = self.serialize_devices()
        print(f"Total Kasa devices (found + cached): {len(device_list)}")
        return device_list

    def get_device_by_alias(self, alias):
        """Finds a device by its alias (case-insensitive)."""
        for ip, dev in self.devices.items():
            dev_alias = dev.get("alias") if isinstance(dev, dict) else getattr(dev, "alias", None)
            if dev_alias and dev_alias.lower() == alias.lower():
                return dev
        return None

    def _resolve_device(self, target):
        """Resolves a target string (IP or Alias) to a device object."""
        # check if it is an IP 
        if target in self.devices:
            dev = self.devices[target]
            return None if self._is_offline_stub(dev) else dev
        
        # Check alias
        dev = self.get_device_by_alias(target)
        if dev and not self._is_offline_stub(dev):
            return dev
            
        return None

    def name_to_hsv(self, color_name):
        """Converts common color names to HSV (Hue, Saturation, Value).
           Hue: 0-360, Sat: 0-100, Val: 0-100
        """
        color_name = color_name.lower().strip()
        colors = {
            "red": (0, 100, 100),
            "orange": (30, 100, 100),
            "yellow": (60, 100, 100),
            "green": (120, 100, 100),
            "cyan": (180, 100, 100),
            "blue": (240, 100, 100),
            "purple": (300, 100, 100),
            "pink": (300, 50, 100),
            "white": (0, 0, 100),
            "warm": (30, 20, 100), # Warm White approx
            "cool": (200, 10, 100), # Cool White approx
            "daylight": (0, 0, 100),
        }
        return colors.get(color_name, None)

    async def turn_on(self, target):
        """Turns on the device (Target: IP or Alias)."""
        dev = self._resolve_device(target)
        if dev:
            try:
                await dev.turn_on()
                await dev.update()
                return True
            except Exception as e:
                print(f"Error turning on {target}: {e}")
                return False
        
        dev = await self._discover_target(target)
        if dev:
            try:
                await dev.turn_on()
                await dev.update()
                return True
            except Exception:
                pass
        return False

    async def turn_off(self, target):
        """Turns off the device (Target: IP or Alias)."""
        dev = self._resolve_device(target)
        if dev:
            try:
                await dev.turn_off()
                await dev.update()
                return True
            except Exception as e:
                print(f"Error turning off {target}: {e}")
                return False
        
        dev = await self._discover_target(target)
        if dev:
            try:
                await dev.turn_off()
                await dev.update()
                return True
            except Exception:
                pass
        return False

    async def set_brightness(self, target, brightness):
        """Sets brightness (0-100)."""
        dev = self._resolve_device(target)
        if not dev:
            dev = await self._discover_target(target)
        if dev and (dev.is_dimmable or dev.is_bulb):
            try:
                await dev.set_brightness(int(brightness))
                await dev.update()
                return True
            except Exception as e:
                 print(f"Error setting brightness for {target}: {e}")
        return False

    async def set_color(self, target, color_input):
        """Sets color by name or direct HSV tuple."""
        dev = self._resolve_device(target)
        if not dev:
            dev = await self._discover_target(target)
        if not dev or not dev.is_color:
            return False

        hsv = None
        if isinstance(color_input, str):
            hsv = self.name_to_hsv(color_input)
        elif isinstance(color_input, (tuple, list)) and len(color_input) == 3:
            hsv = color_input
        
        if hsv:
            try:
                # Kasa expects Hue (0-360), Sat (0-100), Val (0-100)
                await dev.set_hsv(int(hsv[0]), int(hsv[1]), int(hsv[2]))
                await dev.update()
                return True
            except Exception as e:
                 print(f"Error setting color for {target}: {e}")
        return False

# Standalone test
if __name__ == "__main__":
    async def main():
        agent = KasaAgent()
        await agent.discover_devices()
        print("Devices:", agent.devices)
        
        # Example Test
        # await agent.turn_on("Bedroom Light")
        # await agent.set_color("Bedroom Light", "Red")
    
    asyncio.run(main())
