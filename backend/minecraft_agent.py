"""
Minecraft Bot Manager - Wrapper for Mineflayer bot subprocess.
Handles communication with Node.js Mineflayer process via IPC (stdio).
"""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class BotStatus:
    """Current bot status snapshot."""
    is_running: bool
    is_connected: bool
    health: float = 20.0
    hunger: float = 20.0
    position: Optional[Dict[str, float]] = None
    dimension: str = "overworld"
    inventory: List[Dict[str, Any]] = None
    username: str = ""
    uuid: str = ""
    
    def __post_init__(self):
        if self.inventory is None:
            self.inventory = []


@dataclass
class PerceptionEvent:
    """Perception event from bot."""
    event_type: str  # 'chat', 'player_join', 'player_leave', 'status_update', 'block_update'
    timestamp: float
    data: Dict[str, Any]


class MinecraftBotManager:
    """Manager for Minecraft bot subprocess."""
    
    def __init__(self, 
                 host: str = "localhost",
                 port: int = 25565,
                 username: str = "strawberryglass",
                 auth: str = "offline",
                 version: str = "1.20.4"):
        """
        Initialize Minecraft Bot Manager.
        
        Args:
            host: Minecraft server host
            port: Minecraft server port
            username: Bot username
            auth: Auth type ('offline', 'microsoft', 'mojang')
            version: Minecraft version
        """
        self.host = host
        self.port = port
        self.username = username
        self.auth = auth
        self.version = version
        
        self._process: Optional[subprocess.Popen] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._is_connected = False
        
        # Status tracking
        self._status = BotStatus(
            is_running=False,
            is_connected=False,
            username=username
        )
        
        # Perception cache
        self._last_perception: Dict[str, Any] = {}
        self._perception_callbacks: List[Callable[[PerceptionEvent], Any]] = []
        
        # Action queue
        self._pending_actions: Dict[str, asyncio.Future] = {}
        self._pending_by_action: Dict[str, List[str]] = {}
        self._pending_by_signature: Dict[str, str] = {}
        
        # Paths
        self._backend_dir = Path(__file__).parent
        self._bot_dir = self._backend_dir / "minecraft-bot"
        
        self.logger = self._setup_logger()
    
    def _setup_logger(self):
        """Setup logger for bot manager."""
        try:
            from loguru import logger as loguru_logger
            return loguru_logger
        except ImportError:
            import logging
            logging.basicConfig(level=logging.INFO)
            return logging.getLogger("MinecraftBotManager")
    
    async def start(self) -> bool:
        """
        Start the Minecraft bot subprocess.
        
        Returns:
            True if successfully started, False otherwise.
        """
        if self._is_running:
            self.logger.warning("Bot is already running")
            return False
        
        if not self._bot_dir.exists():
            self.logger.error(f"Bot directory not found: {self._bot_dir}")
            return False
        
        try:
            # Check if minecraft-bot is set up
            bot_index = self._bot_dir / "index.js"
            if not bot_index.exists():
                self.logger.error(f"Bot entry point not found: {bot_index}")
                return False
            
            # Set environment variables for bot
            env = os.environ.copy()
            env["MC_HOST"] = self.host
            env["MC_PORT"] = str(self.port)
            env["MC_USERNAME"] = self.username
            env["MC_AUTH"] = self.auth
            env["MC_VERSION"] = self.version
            
            self.logger.info(f"Starting bot: node index.js")
            self.logger.info(f"Connecting to {self.host}:{self.port} as {self.username}")
            
            # Use asyncio subprocess (non-blocking)
            self._process = await asyncio.create_subprocess_exec(
                "node",
                str(bot_index),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                stdin=asyncio.subprocess.PIPE,
                cwd=str(self._bot_dir),
                env=env
            )
            
            self._is_running = True
            self._status.is_running = True
            
            # Start reader task (non-blocking async reader)
            self._reader_task = asyncio.create_task(self._read_subprocess_output())
            
            self.logger.info("Bot subprocess started successfully")
            
            # Give bot a moment to start up
            await asyncio.sleep(0.5)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start bot: {e}")
            self._is_running = False
            self._status.is_running = False
            return False
    
    async def stop(self) -> bool:
        """
        Stop the Minecraft bot subprocess.
        
        Returns:
            True if successfully stopped, False otherwise.
        """
        if not self._is_running:
            self.logger.warning("Bot is not running")
            return False
        
        try:
            if self._process:
                # Send stop command
                await self.send_action("stop", {}, wait_for_result=False)
                
                # Wait a bit for graceful shutdown
                await asyncio.sleep(1.0)
                
                # Kill if still running
                if self._process.returncode is None:
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                    
                if self._process.returncode is None:
                    self._process.kill()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
            
            self._is_running = False
            self._is_connected = False
            self._status.is_running = False
            self._status.is_connected = False
            
            if self._reader_task:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass
            
            self.logger.info("Bot stopped successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop bot: {e}")
            return False
    
    async def send_action(
        self,
        action_name: str,
        params: Dict[str, Any],
        wait_for_result: bool = True,
        timeout_seconds: float = 15.0,
    ) -> Dict[str, Any]:
        """
        Send action to bot subprocess (non-blocking async).
        
        Args:
            action_name: Name of the action to execute
            params: Action parameters
            
        Returns:
            Action result payload with success/error details.
        """
        if not self._is_running or not self._process or not self._process.stdin:
            self.logger.error(f"Bot is not running (is_running={self._is_running}, process={self._process}, stdin={self._process.stdin if self._process else None})")
            return {
                "success": False,
                "error": "Bot is not running",
                "action": action_name,
            }
        
        heavy_actions = {"collectBlocks", "collect_blocks", "mine_ore", "hunt_mobs"}
        medium_actions = {"craft_recipe", "navigate_to_location", "move_to_position"}
        effective_timeout = timeout_seconds
        if timeout_seconds <= 15.0:
            if action_name in heavy_actions:
                effective_timeout = 60.0
            elif action_name in medium_actions:
                effective_timeout = 30.0

        action_signature = self._action_signature(action_name, params)

        # Coalesce duplicated action+params calls while one is in flight.
        if wait_for_result:
            existing_id = self._pending_by_signature.get(action_signature)
            if existing_id:
                existing_future = self._pending_actions.get(existing_id)
                if existing_future and not existing_future.done():
                    try:
                        return await asyncio.wait_for(asyncio.shield(existing_future), timeout=effective_timeout)
                    except asyncio.TimeoutError:
                        return {
                            "success": False,
                            "action": action_name,
                            "error": f"Action timed out after {effective_timeout:.1f}s",
                            "request_id": existing_id,
                        }

        request_id = str(uuid.uuid4())
        future: Optional[asyncio.Future] = None
        try:
            if wait_for_result:
                future = asyncio.get_running_loop().create_future()
                self._pending_actions[request_id] = future
                self._pending_by_action.setdefault(action_name, []).append(request_id)
                self._pending_by_signature[action_signature] = request_id

            action = {
                "type": "action",
                "action": action_name,
                "params": params,
                "request_id": request_id,
                "timestamp": datetime.now().isoformat()
            }
            
            json_line = json.dumps(action) + "\n"
            self.logger.info(f"[BOT] Sending action to subprocess: {action_name}")
            self._process.stdin.write(json_line.encode())
            await self._process.stdin.drain()  # Async flush
            
            self.logger.debug(f"Action sent successfully: {action_name} with params: {params}")

            if not wait_for_result:
                return {
                    "success": True,
                    "action": action_name,
                    "message": "Action sent",
                    "request_id": request_id,
                }

            try:
                result = await asyncio.wait_for(future, timeout=effective_timeout)
                return result
            except asyncio.TimeoutError:
                self._remove_pending_action(request_id, action_name)
                return {
                    "success": False,
                    "action": action_name,
                    "error": f"Action timed out after {effective_timeout:.1f}s",
                    "request_id": request_id,
                }
            
        except Exception as e:
            self._remove_pending_action(request_id, action_name)
            self.logger.error(f"Failed to send action: {e}")
            return {
                "success": False,
                "action": action_name,
                "error": str(e),
                "request_id": request_id,
            }

    def _remove_pending_action(self, request_id: str, action_name: Optional[str] = None):
        """Remove pending action bookkeeping safely."""
        self._pending_actions.pop(request_id, None)
        if action_name and action_name in self._pending_by_action:
            ids = self._pending_by_action.get(action_name, [])
            if request_id in ids:
                ids.remove(request_id)
            if not ids:
                self._pending_by_action.pop(action_name, None)
        # Remove signature mapping that points to this request id.
        stale_signatures = [sig for sig, rid in self._pending_by_signature.items() if rid == request_id]
        for sig in stale_signatures:
            self._pending_by_signature.pop(sig, None)

    def _action_signature(self, action_name: str, params: Dict[str, Any]) -> str:
        """Stable signature for deduplicating repeated actions with the same params."""
        try:
            params_key = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
        except Exception:
            params_key = str(params)
        return f"{action_name}:{params_key}"

    def _resolve_pending_action(self, request_id: str, payload: Dict[str, Any]):
        """Resolve a pending action future if present."""
        fut = self._pending_actions.get(request_id)
        if fut and not fut.done():
            fut.set_result(payload)
    
    async def _read_subprocess_output(self):
        """Reader loop for subprocess stdout (non-blocking async)."""
        if not self._process or not self._process.stdout:
            return
        
        try:
            while self._is_running:
                try:
                    # Async readline - won't block event loop
                    line = await self._process.stdout.readline()
                    if not line:
                        break
                    
                    line = line.decode().strip() if isinstance(line, bytes) else line.strip()
                    if not line:
                        continue
                    
                    # Parse JSON perception event
                    try:
                        event_data = json.loads(line)
                        await self._handle_perception_event(event_data)
                    except json.JSONDecodeError:
                        # Log non-JSON output
                        self.logger.debug(f"Bot output: {line}")
                        
                except Exception as e:
                    self.logger.error(f"Error reading subprocess output: {e}")
                    break
        
        except Exception as e:
            self.logger.error(f"Reader task failed: {e}")
        finally:
            self._is_running = False
            self._is_connected = False
            # Fail any pending action waits when subprocess reader exits.
            for request_id, fut in list(self._pending_actions.items()):
                if not fut.done():
                    fut.set_result({
                        "success": False,
                        "error": "Bot subprocess disconnected",
                        "request_id": request_id,
                    })
            self._pending_actions.clear()
            self._pending_by_action.clear()
            self._pending_by_signature.clear()
    
    
    async def _handle_perception_event(self, event_data: Dict[str, Any]):
        """Handle perception event from bot."""
        try:
            event_type = event_data.get("type", "unknown")
            data = event_data.get("data", {}) or {}
            
            if event_type == "ready":
                self._is_connected = True
                self._status.is_connected = True
                self.logger.info("Bot connected to server")
                
            elif event_type == "status_update":
                # Update cached status
                self._status.health = data.get("health", self._status.health)
                self._status.hunger = data.get("hunger", self._status.hunger)
                self._status.position = data.get("position", self._status.position)
                self._status.dimension = data.get("dimension", self._status.dimension)
                self._status.inventory = data.get("inventory", self._status.inventory)
                self._last_perception["status"] = asdict(self._status)
                
            elif event_type == "chat":
                username = data.get("username")
                message = data.get("message")
                self.logger.info(f"[CHAT] {username}: {message}")
                self._last_perception["last_chat"] = {
                    "username": username,
                    "message": message,
                    "timestamp": datetime.now().isoformat()
                }
                
            elif event_type == "error":
                error_msg = data.get("message") or event_data.get("message", "Unknown error")
                self.logger.error(f"Bot error: {error_msg}")

            # Resolve pending action futures from action_result/error events.
            if event_type in {"action_result", "error"}:
                request_id = data.get("request_id")
                action_name = data.get("action")

                payload = {
                    "success": bool(data.get("success", event_type == "action_result")),
                    "action": action_name,
                    "message": data.get("message"),
                    "data": data.get("data"),
                    "error": data.get("message") if event_type == "error" else data.get("error"),
                    "request_id": request_id,
                }

                if request_id and request_id in self._pending_actions:
                    self._resolve_pending_action(request_id, payload)
                    self._remove_pending_action(request_id, action_name)
                elif action_name and action_name in self._pending_by_action and self._pending_by_action[action_name]:
                    fallback_request_id = self._pending_by_action[action_name].pop(0)
                    self._resolve_pending_action(fallback_request_id, payload)
                    self._remove_pending_action(fallback_request_id, action_name)
            
            # Call registered callbacks
            if event_type != "status_update":  # Don't spam callbacks
                perception = PerceptionEvent(
                    event_type=event_type,
                    timestamp=datetime.now().timestamp(),
                    data=data
                )
                
                for callback in self._perception_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(perception)
                        else:
                            callback(perception)
                    except Exception as e:
                        self.logger.error(f"Perception callback error: {e}")
        
        except Exception as e:
            self.logger.error(f"Failed to handle perception event: {e}")
    
    def get_status(self) -> BotStatus:
        """Get current bot status."""
        return self._status
    
    def get_perception_snapshot(self) -> Dict[str, Any]:
        """Get perception cache snapshot."""
        return dict(self._last_perception)
    
    def register_perception_callback(self, callback: Callable[[PerceptionEvent], Any]):
        """Register callback for perception events."""
        self._perception_callbacks.append(callback)
    
    def unregister_perception_callback(self, callback: Callable[[PerceptionEvent], Any]):
        """Unregister perception callback."""
        if callback in self._perception_callbacks:
            self._perception_callbacks.remove(callback)

