# Troubleshooting

Common issues and solutions for MonikAI.

## Backend Issues

### Backend Won't Start

**Error:** `Address already in use :8000`

**Solution:**
```bash
# Find and kill process using port 8000
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Or use different port
python -m uvicorn backend.core.server:app --port 8001
```

---

### ImportError: No module named 'fastapi'

**Cause:** Virtual environment not activated or dependencies not installed

**Solution:**
```bash
# Activate venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

### Gemini API Error: Invalid API key

**Error:** `google.auth.exceptions.InvalidValue: API key provided is invalid`

**Solution:**
1. Get new key from [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Update `.env`:
   ```
   GEMINI_API_KEY=your_new_key
   ```
3. Restart backend

**Verify key works:**
```bash
python -c "import os; print(os.getenv('GEMINI_API_KEY'))"
```

---

### Audio Input Not Working

**Error:** No audio captured from microphone

**Solution:**
1. Check device has microphone: `python -m sounddevice --list`
2. Grant browser microphone permission
3. Check system audio settings
4. Try different audio device:
   ```python
   # backend/audio/manual_start_audio.py
   # Change device_index to different number
   ```

---

### Socket.IO Connection Failed

**Error:** WebSocket connection refused

**Solution:**
1. Ensure backend running: `http://localhost:8000/docs`
2. Check firewall not blocking port 8000
3. Check CORS is enabled in `server.py`

---

### Database Lock Error

**Error:** `sqlite3.OperationalError: database is locked`

**Cause:** Multiple processes accessing SQLite simultaneously

**Solution:**
1. Ensure only one backend instance running
2. Restart backend: `Ctrl+C` then run again
3. Check `data/user_memory/` folder has write permissions

---

### Memory File Corruption

**Error:** `JSONDecodeError: Expecting value` when loading personality state

**Solution:**
```bash
# Backup corrupted state
copy data\user_memory\personality_state.json data\user_memory\personality_state.json.backup

# Reset state
rm data\user_memory\*.json

# Restart backend - will run onboarding again
```

---

## Frontend Issues

### Frontend Can't Connect to Backend

**Error:** Connection timeout or `GET http://localhost:8000/status 404`

**Solution:**
1. Verify backend running: `http://localhost:8000/docs` in browser
2. Check `.env` has correct backend URL
3. Restart frontend: Kill `npm run dev` and restart

---

### Blank Screen / No Components Loading

**Error:** White page with no errors

**Solution:**
1. Check browser console (F12 → Console tab)
2. Look for JavaScript errors
3. Try hard refresh: `Ctrl+Shift+R`
4. Clear browser cache:
   ```bash
   # Clear LocalStorage
   # F12 → Application → LocalStorage → Clear All
   ```

---

### Audio Not Playing

**Error:** Response received but no sound

**Solution:**
1. Check system volume not muted
2. Check browser volume in Google Chrome (speaker icon)
3. Grant browser permission to play audio
4. Test with different browser

**Debug audio:**
```javascript
// In browser console
console.log(navigator.mediaDevices); // Check if audio available
```

---

### React Hot Reload Not Working

**Error:** Changes don't reflect in browser without full refresh

**Cause:** Vite HMR issue

**Solution:**
```bash
# Kill npm process
# Ctrl+C

# Clear cache and restart
rm -r node_modules/.vite
npm run dev
```

---

### Performance Issues - Slow Typing

**Error:** Visible lag when typing

**Cause:** React rendering bottleneck

**Solution:**
1. Check browser performance (F12 → Performance tab)
2. Disable extensions slowing page
3. Update React DevTools
4. Restart frontend

---

### Personality State Not Updating

**Error:** Mood doesn't change after messages

**Cause:** Personality observation not triggered

**Debug steps:**
1. Check backend logs for `observe_message` calls
2. Verify progression system running:
   ```python
   # backend/test_personality_state.py
   python backend/test_personality_state.py
   ```
3. Check `data/user_memory/personality_state.json` is being written

---

## Integration Issues

### Minecraft Bot Won't Connect

**Error:** `Connection refused` or `Invalid server address`

**Solution:**
1. Verify Minecraft server running and reachable
2. Check server address in `.env`: `MINECRAFT_SERVER=localhost:25565`
3. Verify firewall not blocking connection
4. Test with Minecraft launcher first

**Debug:**
```bash
node minecraft-bot/index.js --test
```

---

### Spotify Connection Failed

**Error:** `401 Unauthorized` or `Invalid credentials`

**Solution:**
1. Re-authorize Spotify:
   ```bash
   # Delete token
   rm data/spotify_tokens.json
   
   # Restart backend and click "Connect Spotify"
   ```
2. Verify client credentials in `.env`
3. Check redirect URI matches: `http://localhost:8000/spotify/callback`

**Verify token:**
```bash
python -c "import json; print(json.load(open('data/spotify_tokens.json')))"
```

---

### Telegram Bot Not Responding

**Error:** Messages sent but no response

**Cause:** Bot token invalid or allowlist issue

**Solution:**
1. Get new token from @BotFather
2. Update `.env`: `TELEGRAM_BOT_TOKEN=new_token`
3. Verify chat ID in allowlist
4. Restart backend

**Check bot working:**
```bash
# Send test message to bot
# Should see in backend logs
```

---

### Kasa Smart Home Devices Not Found

**Error:** No devices discovered on network

**Solution:**
1. Ensure TP-Link device on same network
2. Check device powered on
3. Verify device IP discoverable:
   ```bash
   python -c "from kasa import Discover; print(Discover.discover())"
   ```
4. Update `.env` with network range: `KASA_NETWORK=192.168.1.0/24`

---

## Data Issues

### User Data Lost After Restart

**Error:** All progress reset

**Cause:** Data not saved or wrong folder

**Solution:**
1. Check `data/user_memory/` folder exists with files
2. Verify filesystem has write permissions
3. Check file permissions:
   ```bash
   ls -la data/user_memory/
   ```
4. Restore from backup if available:
   ```bash
   cp -r data/user_memory_backup/* data/user_memory/
   ```

---

### Session Files Not Being Created

**Error:** Conversations not logged

**Cause:** Session directory doesn't exist or not writable

**Solution:**
```bash
# Create directories
mkdir -p data/sessions
mkdir -p data/user_memory
mkdir -p data/memory

# Verify permissions
chmod 755 data/sessions
chmod 755 data/user_memory
chmod 755 data/memory

# Restart backend
```

---

### Memory Retrieval Not Working

**Error:** Memory search returns no results

**Cause:** SQLite FTS index not built or corrupted

**Solution:**
```bash
# Rebuild index
python -c "from backend.ai.memory_engine import MemoryEngine; m = MemoryEngine(); m.rebuild_index()"

# Or clear and rebuild
rm data/user_memory/memory_index.db
# Restart backend - index rebuilds automatically
```

---

## Browser Issues

### CORS Error: Access Denied

**Error:** `No 'Access-Control-Allow-Origin' header`

**Cause:** Frontend and backend on different domains

**Solution:**
1. Ensure both on localhost
2. Check CORS enabled in `backend/core/server.py`
3. Add origin if needed:
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:5173"],
       ...
   )
   ```

---

### Browser Crashes on Load

**Error:** Tab crashes or unresponsive

**Cause:** Memory leak or infinite loop

**Solution:**
1. Check browser console for errors
2. Disable all extensions
3. Try incognito mode
4. Clear browser cache completely

---

## Performance Optimization

### Slow Backend Response Time

**Cause:** Personality system or progression system expensive

**Solution:**
1. Profile with:
   ```bash
   pip install py-spy
   py-spy record -o profile.svg -- python -m uvicorn ...
   ```
2. Identify bottleneck
3. Check if progression.observe_message() taking too long
4. Consider caching results

---

### High Memory Usage

**Cause:** Memory leak in session or context manager

**Solution:**
1. Monitor with:
   ```bash
   # In backend
   import tracemalloc
   tracemalloc.start()
   ```
2. Check for unclosed resources (file handles, connections)
3. Restart backend if memory keeps growing

---

## Getting Help

### Check Logs

**Backend logs:**
```
Print to terminal where `python -m uvicorn` running
Set DEBUG=1 environment variable for more verbose logs
```

**Frontend logs:**
- Open browser DevTools (F12)
- Check Console tab for errors
- Check Network tab for failed requests

### Report Issue

1. Check [similar issues](https://github.com/yourusername/monikai/issues)
2. Collect information:
   - Python version: `python --version`
   - Node version: `node --version`
   - OS: Windows/Mac/Linux
   - Error message (full)
   - Steps to reproduce
3. Create [new issue](https://github.com/yourusername/monikai/issues/new)

### Enable Verbose Logging

```bash
# Python backend
export DEBUG=1
python -m uvicorn backend.core.server:app --reload

# Or Windows
set DEBUG=1
python -m uvicorn backend.core.server:app --reload
```

---

**Need More Help?** Check [Architecture](./Architecture.md) or [API Reference](./API-Reference.md) | [Home](./Home.md)
