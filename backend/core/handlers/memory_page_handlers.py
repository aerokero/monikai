from datetime import datetime
from pathlib import Path


def register_memory_page_handlers(
    sio,
    *,
    data_dir,
    resolve_memory_page,
    list_memory_pages,
    get_audio_loop,
):
    @sio.event
    async def save_memory(sid, data):
        try:
            messages = data.get('messages', [])
            if not messages:
                print("No messages to save.")
                return

            memory_dir = data_dir / "long_term_memory"
            memory_dir.mkdir(exist_ok=True)

            provided_name = data.get('filename')

            if provided_name:
                if not provided_name.endswith('.txt'):
                    provided_name += '.txt'
                filename = memory_dir / Path(provided_name).name
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = memory_dir / f"memory_{timestamp}.txt"

            with open(filename, 'w', encoding='utf-8') as f:
                for msg in messages:
                    sender = msg.get('sender', 'Unknown')
                    text = msg.get('text', '')
                    f.write(f"{sender}: {text}\n")
            print(f"Conversation saved to {filename}")
            await sio.emit('status', {'msg': 'Memory Saved Successfully'}, room=sid)

        except Exception as e:
            print(f"Error saving memory: {e}")
            await sio.emit('error', {'msg': f"Failed to save memory: {str(e)}"}, room=sid)

    @sio.event
    async def memory_get_page(sid, data):
        try:
            path = (data or {}).get("path") or "notes.md"
            p = resolve_memory_page(path)
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("", encoding="utf-8")
            text = p.read_text(encoding="utf-8", errors="ignore")
            await sio.emit('memory_page', {'path': str(p), 'text': text}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to read memory page: {e}"}, room=sid)

    @sio.event
    async def memory_list_pages(sid, data=None):
        try:
            pages = list_memory_pages()
            await sio.emit('memory_pages', {'pages': pages}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to list memory pages: {e}"}, room=sid)

    @sio.event
    async def memory_create_page(sid, data):
        try:
            path = (data or {}).get("path") or "notes.md"
            title = (data or {}).get("title") or ""
            p = resolve_memory_page(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                if title:
                    p.write_text(f"# {title}\n\n", encoding="utf-8")
                else:
                    p.write_text("", encoding="utf-8")
            text = p.read_text(encoding="utf-8", errors="ignore")
            await sio.emit('memory_page', {'path': str(p), 'text': text}, room=sid)
            await sio.emit('memory_pages', {'pages': list_memory_pages()}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to create memory page: {e}"}, room=sid)

    @sio.event
    async def memory_set_page(sid, data):
        try:
            path = (data or {}).get("path") or "notes.md"
            content = (data or {}).get("content", "")
            p = resolve_memory_page(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content or "", encoding="utf-8")
            await sio.emit('memory_page', {'path': str(p), 'text': content or ""}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to write memory page: {e}"}, room=sid)

    @sio.event
    async def memory_delete_page(sid, data):
        try:
            path = (data or {}).get("path") or ""
            if not path:
                return
            p = resolve_memory_page(path)
            if p.exists():
                p.unlink()
            await sio.emit('memory_pages', {'pages': list_memory_pages()}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to delete memory page: {e}"}, room=sid)

    @sio.event
    async def memory_rename_page(sid, data):
        try:
            path = (data or {}).get("path") or ""
            new_path = (data or {}).get("new_path") or ""
            title = (data or {}).get("title") or ""
            if not path:
                return
            src = resolve_memory_page(path)
            if not src.exists():
                await sio.emit('error', {'msg': "Memory page not found."}, room=sid)
                return
            dest = resolve_memory_page(new_path or path)
            if dest.exists() and dest != src:
                await sio.emit('error', {'msg': "Target note already exists."}, room=sid)
                return
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest != src:
                src.rename(dest)
            text = dest.read_text(encoding="utf-8", errors="ignore")
            if title and dest.suffix.lower() == ".md":
                lines = text.splitlines()
                replaced = False
                for idx, line in enumerate(lines):
                    if line.strip():
                        if line.lstrip().startswith("#"):
                            lines[idx] = f"# {title}"
                            replaced = True
                        break
                if not replaced:
                    lines = [f"# {title}", ""] + lines
                text = "\n".join(lines)
                if text and not text.endswith("\n"):
                    text += "\n"
                dest.write_text(text, encoding="utf-8")
            await sio.emit('memory_page', {'path': str(dest), 'text': text}, room=sid)
            await sio.emit('memory_pages', {'pages': list_memory_pages()}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to rename memory page: {e}"}, room=sid)

    @sio.event
    async def memory_append_page(sid, data):
        try:
            path = (data or {}).get("path") or "notes.md"
            content = (data or {}).get("content", "")
            p = resolve_memory_page(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                if content and not content.startswith("\n"):
                    f.write("\n")
                f.write(content)
                if content and not content.endswith("\n"):
                    f.write("\n")
            text = p.read_text(encoding="utf-8", errors="ignore")
            await sio.emit('memory_page', {'path': str(p), 'text': text}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to append memory page: {e}"}, room=sid)

    @sio.event
    async def upload_memory(sid, data):
        print(f"Received memory upload request")
        try:
            memory_text = data.get('memory', '')
            if not memory_text:
                print("No memory data provided.")
                return

            audio_loop = get_audio_loop()
            if not audio_loop:
                print("[SERVER DEBUG] [Error] Audio loop is None. Cannot load memory.")
                await sio.emit('error', {'msg': "System not ready (Audio Loop inactive)"}, room=sid)
                return

            if not audio_loop.session:
                print("[SERVER DEBUG] [Error] Session is None. Cannot load memory.")
                await sio.emit('error', {'msg': "System not ready (No active session)"}, room=sid)
                return

            print("Sending memory context to model...")
            context_msg = f"System Notification: The user has uploaded a long-term memory file. Please load the following context into your understanding. The format is a text log of previous conversations:\n\n{memory_text}"

            await audio_loop.session.send(input=context_msg, end_of_turn=True)
            print("Memory context sent successfully.")
            await sio.emit('status', {'msg': 'Memory Loaded into Context'}, room=sid)

        except Exception as e:
            print(f"Error uploading memory: {e}")
            await sio.emit('error', {'msg': f"Failed to upload memory: {str(e)}"}, room=sid)
