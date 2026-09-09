"""Odysseus Backend Bridge for MonikAI.
Mounts the complete native Odysseus AI backend infrastructure (SQLAlchemy DB,
Model Discovery, Email, Calendar, Notes, Documents, Tasks, MCP, Vault, Settings).
"""

import logging
import json
import os
import sys
from pathlib import Path
from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Ensure Odysseus modules can be imported
_ODY_ROOT = Path(__file__).resolve().parent / "odysseus"
if str(_ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(_ODY_ROOT))

# Ensure persistent data dir and auth settings are configured
os.environ["AUTH_ENABLED"] = "false"


def _ensure_builtin_model_endpoints() -> None:
    """Back the picker aliases with real native Odysseus endpoints.

    The public picker intentionally exposes stable ids (``gemini-text`` and
    ``ollama-local``).  Native chat routes, however, resolve endpoint ids via
    ``ModelEndpoint``.  Keeping the adapter rows here lets the native route
    remain authoritative without exposing provider plumbing in the UI.
    """
    from core.database import ModelEndpoint, SessionLocal

    definitions = (
        {
            "id": "gemini-text",
            "name": "Google Gemini",
            "base_url": os.getenv(
                "GEMINI_OPENAI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai",
            ).rstrip("/"),
            "api_key": os.getenv("GEMINI_API_KEY") or None,
            "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
            "endpoint_kind": "api",
        },
        {
            "id": "ollama-local",
            "name": "Local Ollama",
            "base_url": os.getenv("OLLAMA_OPENAI_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
            "api_key": None,
            "models": ["llama3.2", "qwen2.5-coder", "mistral"],
            "endpoint_kind": "local",
        },
    )

    db = SessionLocal()
    try:
        for definition in definitions:
            row = db.query(ModelEndpoint).filter(ModelEndpoint.id == definition["id"]).first()
            if row is None:
                row = ModelEndpoint(
                    id=definition["id"],
                    name=definition["name"],
                    base_url=definition["base_url"],
                    api_key=definition["api_key"],
                    is_enabled=True,
                    cached_models=json.dumps(definition["models"]),
                    model_type="llm",
                    endpoint_kind=definition["endpoint_kind"],
                    model_refresh_mode="manual",
                    supports_tools=True,
                    owner=None,
                )
                db.add(row)
                continue

            # Repair rows created by an earlier bridge version, but do not
            # overwrite an operator's explicit endpoint configuration.
            if row.base_url in ("", "/api/chat_stream", None):
                row.base_url = definition["base_url"]
            if definition["id"] == "gemini-text" and os.getenv("GEMINI_API_KEY"):
                row.api_key = os.getenv("GEMINI_API_KEY")
            if not row.cached_models:
                row.cached_models = json.dumps(definition["models"])
        db.commit()
    finally:
        db.close()

def init_and_register_odysseus_backend(app: FastAPI):
    """Initializes all Odysseus components and mounts full native routers."""
    try:
        import core.database as db
        db.init_db()
        logger.info("Odysseus database initialized at %s", os.environ.get("ODYSSEUS_DATA_DIR"))
        _ensure_builtin_model_endpoints()

        from src.constants import BASE_DIR, REQUEST_TIMEOUT, OPENAI_API_KEY, SESSIONS_FILE
        from src.app_initializer import initialize_managers
        
        # 1. Initialize all core managers & handlers
        components = initialize_managers(BASE_DIR)
        app.state.odysseus_components = components
        session_manager = components["session_manager"]
        memory_manager = components["memory_manager"]
        memory_vector = components.get("memory_vector")
        skills_manager = components["skills_manager"]
        upload_handler = components["upload_handler"]
        api_key_manager = components["api_key_manager"]
        preset_manager = components["preset_manager"]
        chat_processor = components["chat_processor"]
        research_handler = components["research_handler"]
        chat_handler = components["chat_handler"]
        model_discovery = components["model_discovery"]

        # The legacy MonikAI HTTP bridge is registered before these native
        # routers and needs the same persona source as the preset UI.  Expose
        # the initialized managers on app.state instead of letting the chat
        # route keep its own hard-coded character prompt.
        app.state.preset_manager = preset_manager
        app.state.chat_handler = chat_handler

        # 2. Task scheduler, Webhook & MCP Managers
        from src.task_scheduler import TaskScheduler
        from src.event_bus import set_task_scheduler
        from src.webhook_manager import WebhookManager
        from src.mcp_manager import McpManager
        from src.agent_tools import set_mcp_manager

        task_scheduler = TaskScheduler(session_manager)
        # Keep the native scheduler on the application so the MonikAI
        # lifespan can start/stop it alongside the rest of the runtime.  The
        # task routes were mounted for a long time without this lifecycle
        # hook, which made scheduled Tasks look healthy in the UI but never
        # execute after a fresh server start.
        app.state.task_scheduler = task_scheduler
        set_task_scheduler(task_scheduler)
        webhook_manager = WebhookManager(api_key_manager=api_key_manager)
        mcp_manager = McpManager()
        set_mcp_manager(mcp_manager)

        # Text conversation belongs to native Odysseus.  Mount this router
        # before the compatibility HTTP bridge so the production
        # /api/chat(_stream) endpoints use the real session, model, persona,
        # tool and memory pipeline instead of the old MonikAI shim.
        app.state.odysseus_native_chat_routes_mounted = False
        try:
            from routes.chat_routes import setup_chat_routes

            app.include_router(setup_chat_routes(
                session_manager=session_manager,
                chat_handler=chat_handler,
                chat_processor=chat_processor,
                memory_manager=memory_manager,
                research_handler=research_handler,
                upload_handler=upload_handler,
                memory_vector=memory_vector,
                webhook_manager=webhook_manager,
                skills_manager=skills_manager,
            ))
            app.state.odysseus_native_chat_routes_mounted = True
            logger.info("Odysseus native chat_routes mounted")
        except Exception as e:
            logger.warning("chat_routes mount error: %s", e, exc_info=True)

        # 3. Auth Manager & Routes
        from core.auth import AuthManager
        from core.constants import AUTH_FILE
        from routes.auth_routes import setup_auth_routes
        auth_manager = AuthManager(AUTH_FILE)
        app.state.auth_manager = auth_manager
        app.include_router(setup_auth_routes(auth_manager))

        # The frontend's Persona tab uses these routes.  They were initialized
        # but never mounted, which made model selection and persona selection
        # look like two competing systems instead of two working layers.
        try:
            from routes.preset_routes import setup_preset_routes
            app.include_router(setup_preset_routes(preset_manager))
            logger.info("Odysseus preset_routes mounted")
        except Exception as e:
            logger.warning("preset_routes mount error: %s", e)

        @app.get("/login")
        async def login_page():
            from fastapi.responses import FileResponse
            login_html = Path("/app/static/login.html")
            if login_html.exists():
                return FileResponse(str(login_html))
            return {"ok": True, "auth_enabled": False}

        # 4. Session Routes & History Routes
        try:
            from routes.session_routes import setup_session_routes
            from routes.history.history_routes import setup_history_routes
            session_config = {
                "REQUEST_TIMEOUT": REQUEST_TIMEOUT,
                "OPENAI_API_KEY": OPENAI_API_KEY,
                "SESSIONS_FILE": SESSIONS_FILE,
            }
            app.include_router(setup_session_routes(
                session_manager,
                session_config,
                webhook_manager=webhook_manager,
                upload_handler=upload_handler,
            ))
            app.include_router(setup_history_routes(session_manager, upload_handler=upload_handler))
            logger.info("Odysseus session & history routes mounted")
        except Exception as e:
            logger.warning("session_routes mount error: %s", e)

        # 5. Mount Models Router (Settings -> Add Models, Providers, Discovery)
        try:
            from routes.model_routes import setup_model_routes
            app.include_router(setup_model_routes(model_discovery))
            logger.info("Odysseus model_routes mounted")
        except Exception as e:
            logger.warning("model_routes mount error: %s", e)

        # 6. Mount Email Router (IMAP/SMTP/Gmail/Outlook/Urgency/Unread)
        try:
            from routes.email_routes import setup_email_routes
            app.include_router(setup_email_routes())
            logger.info("Odysseus email_routes mounted")
        except Exception as e:
            logger.warning("email_routes mount error: %s", e)

        # 7. Mount Calendar Router (CalDAV/ICS/Events)
        try:
            from routes.calendar_routes import setup_calendar_routes
            app.include_router(setup_calendar_routes(upload_handler=upload_handler))
            logger.info("Odysseus calendar_routes mounted")
        except Exception as e:
            logger.warning("calendar_routes mount error: %s", e)

        # 8. Mount Notes Router
        try:
            from routes.note.note_routes import setup_note_routes
            app.include_router(setup_note_routes(task_scheduler, upload_handler=upload_handler))
            logger.info("Odysseus note_routes mounted")
        except Exception as e:
            logger.warning("note_routes mount error: %s", e)

        # 9. Mount Documents / Artifacts Router
        try:
            from routes.document.document_routes import setup_document_routes
            app.include_router(setup_document_routes(session_manager, upload_handler))
            logger.info("Odysseus document_routes mounted")
        except Exception as e:
            logger.warning("document_routes mount error: %s", e)

        # 10. Mount Task & Notifications Router
        try:
            from routes.task.task_routes import setup_task_routes
            app.include_router(setup_task_routes(task_scheduler))
            logger.info("Odysseus task_routes mounted")
        except Exception as e:
            logger.warning("task_routes mount error: %s", e)

        # 11. Mount Deep Research Router
        try:
            from routes.research.research_routes import setup_research_routes
            app.include_router(setup_research_routes(research_handler, session_manager=session_manager))
            logger.info("Odysseus research_routes mounted")
        except Exception as e:
            logger.warning("research_routes mount error: %s", e)

        # 12. Mount User Preferences & Settings Router
        try:
            from routes.prefs_routes import setup_prefs_routes
            app.include_router(setup_prefs_routes())
            logger.info("Odysseus prefs_routes mounted")
        except Exception as e:
            logger.warning("prefs_routes mount error: %s", e)

        # 13. Mount Vault & Secure Storage Router
        try:
            from routes.vault.vault_routes import setup_vault_routes
            app.include_router(setup_vault_routes())
            logger.info("Odysseus vault_routes mounted")
        except Exception as e:
            logger.warning("vault_routes mount error: %s", e)

        # 14. Mount Contacts Router (CardDAV)
        try:
            from routes.contacts.contacts_routes import setup_contacts_routes
            app.include_router(setup_contacts_routes())
            logger.info("Odysseus contacts_routes mounted")
        except Exception as e:
            logger.warning("contacts_routes mount error: %s", e)

        # 15. Mount Memory Router
        try:
            from routes.memory.memory_routes import setup_memory_routes
            app.include_router(setup_memory_routes(memory_manager, session_manager, memory_vector=memory_vector))
            logger.info("Odysseus memory_routes mounted")
        except Exception as e:
            logger.warning("memory_routes mount error: %s", e)

        # 16. Mount MCP & Skills Router
        try:
            from routes.mcp.mcp_routes import setup_mcp_routes
            from routes.skills_routes import setup_skills_routes
            app.include_router(setup_mcp_routes(mcp_manager))
            app.include_router(setup_skills_routes(skills_manager))
            logger.info("Odysseus MCP & skills routes mounted")
        except Exception as e:
            logger.warning("mcp/skills mount error: %s", e)

        # 17. Mount Gallery Router
        try:
            from routes.gallery.gallery_routes import setup_gallery_routes
            app.include_router(setup_gallery_routes())
            logger.info("Odysseus gallery_routes mounted")
        except Exception as e:
            logger.warning("gallery_routes mount error: %s", e)

        # 18. Mount Hardware Fit / Cookbook Router
        try:
            from routes.hwfit_routes import setup_hwfit_routes
            from routes.cookbook_routes import setup_cookbook_routes
            app.include_router(setup_hwfit_routes())
            app.include_router(setup_cookbook_routes())
            logger.info("Odysseus hwfit & cookbook routes mounted")
        except Exception as e:
            logger.warning("hwfit/cookbook mount error: %s", e)

        # 19. Diagnostics (service health and terminal log viewer)
        try:
            from routes.diagnostics_routes import setup_diagnostics_routes

            personal_docs_manager = getattr(chat_processor, "personal_docs_manager", None)
            rag_manager = getattr(personal_docs_manager, "rag_manager", None)
            app.include_router(setup_diagnostics_routes(
                rag_manager=rag_manager,
                rag_available=bool(rag_manager and getattr(rag_manager, "healthy", True)),
                research_handler=research_handler,
                memory_vector=memory_vector,
            ))
            logger.info("diagnostics_routes mounted")
        except Exception as e:
            logger.warning("diagnostics_routes mount error: %s", e)

        logger.info("Odysseus backend full suite successfully initialized and mounted!")

    except Exception as err:
        logger.error("Failed to initialize Odysseus backend bridge: %s", err, exc_info=True)
