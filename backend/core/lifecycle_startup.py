import asyncio
from dataclasses import asdict

from ..agents.hue_agent import HueAgent
from ..agents.home_assistant_agent import HomeAssistantAgent
from ..agents.spotify_manager import SpotifyManager
from ..integrations.games.minecraft_agent import MinecraftBotManager
from .runtimes.minecraft_runtime import load_minecraft_bot_config


async def initialize_smart_home_agents(kasa_agent, settings: dict):
    kasa_devices = settings.get("smart_home", {}).get("kasa", {}).get("devices", []) or settings.get("kasa_devices", [])
    if kasa_devices and kasa_agent:
        print("[SERVER] Startup: Initializing Kasa Agent...")
        await kasa_agent.initialize()
    else:
        kasa_agent = None

    hue_config = settings.get("smart_home", {}).get("hue", {})
    if hue_config.get("bridge_ip") and hue_config.get("api_key"):
        print("[SERVER] Startup: Initializing Hue Agent...")
        hue_agent = HueAgent(
            bridge_ip=hue_config.get("bridge_ip"),
            api_key=hue_config.get("api_key"),
        )
        await hue_agent.initialize()
    else:
        hue_agent = None

    print("[SERVER] Startup: Initializing Home Assistant Agent...")
    ha_config = settings.get("smart_home", {}).get("home_assistant", {})
    home_assistant_agent = HomeAssistantAgent(
        ha_url=ha_config.get("url"),
        ha_token=ha_config.get("token"),
        entities_filter=ha_config.get("entities_filter", ["light.*", "switch.*", "scene.*"]),
    )
    await home_assistant_agent.initialize()

    return hue_agent, home_assistant_agent


def initialize_spotify_manager(data_dir):
    try:
        spotify_manager = SpotifyManager(data_dir=data_dir)
        st = spotify_manager.status()
        print(
            "[SERVER] Spotify Manager initialized. "
            f"configured={st.get('configured')} connected={st.get('connected')}"
        )
        if st.get("connected"):
            try:
                spotify_manager.refresh_access_token()
            except Exception as e:
                print(f"[SERVER] Spotify token refresh skipped/failed at startup: {e}")
        return spotify_manager
    except Exception as e:
        print(f"[SERVER] Spotify Manager init failed: {e}")
        return None


def initialize_minecraft_bot_manager(server_file_path):
    try:
        mc_config = load_minecraft_bot_config(server_file_path)

        mc_host = mc_config.get("MC_HOST", "localhost")
        mc_port = int(mc_config.get("MC_PORT", "25565"))
        mc_username = mc_config.get("MC_USERNAME", "strawberryglass")
        mc_auth = mc_config.get("MC_AUTH", "offline")
        mc_version = mc_config.get("MC_VERSION", "1.20.4")

        minecraft_bot_manager = MinecraftBotManager(
            host=mc_host,
            port=mc_port,
            username=mc_username,
            auth=mc_auth,
            version=mc_version,
        )

        print(
            "[SERVER] Minecraft Bot Manager initialized. "
            f"host={mc_host}:{mc_port} username={mc_username}"
        )
        return minecraft_bot_manager
    except Exception as e:
        print(f"[SERVER] Minecraft Bot Manager init failed: {e}")
        return None


def initialize_reminder_and_personality(
    monikai_module,
    user_memory_dir,
    *,
    schedule_emit_to_frontend,
    serialize_reminders,
    get_audio_loop,
    emit_to_frontend,
    get_main_loop,
):
    async def on_reminder_fired_server(rem):
        payload = {
            "id": rem.id,
            "message": rem.message,
            "when_iso": rem.when_iso,
            "speak": bool(rem.speak),
            "alert": bool(getattr(rem, "alert", True)),
        }
        schedule_emit_to_frontend("reminder_fired", payload)
        schedule_emit_to_frontend("reminders_list", {"reminders": serialize_reminders()})

        audio_loop = get_audio_loop()
        if audio_loop:
            await audio_loop.handle_reminder_fired(rem)

    reminder_manager = monikai_module.ReminderManager(
        get_time_context_fn=monikai_module.get_time_context,
        storage_dir=user_memory_dir,
        on_reminder=on_reminder_fired_server,
    )
    reminder_manager.load()
    print("[SERVER] Reminder Manager initialized.")

    personality_system = None
    print("[SERVER] Personality System bypassed in V2.")

    return reminder_manager, personality_system


def initialize_calendar_manager(monikai_module, user_memory_dir, *, schedule_emit_to_frontend):
    calendar_manager_ref = {"manager": None}

    def on_calendar_update_server():
        manager = calendar_manager_ref.get("manager")
        if manager:
            events = [e.__dict__ for e in manager.get_all_events()]
            schedule_emit_to_frontend("calendar_data", events)

    calendar_manager = monikai_module.CalendarManager(
        storage_dir=user_memory_dir,
        on_update=on_calendar_update_server,
    )
    calendar_manager_ref["manager"] = calendar_manager
    calendar_manager.load()
    print("[SERVER] Calendar Manager initialized.")
    return calendar_manager
