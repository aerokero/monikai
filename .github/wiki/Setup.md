# Setup & Installation

Complete guide to setting up and running MonikAI.

## System Requirements

- **OS:** Windows 10+, macOS, or Linux
- **Python:** 3.10+
- **Node.js:** 18.x or newer
- **RAM:** 4GB minimum (8GB recommended)
- **Disk Space:** 2GB free
- **GPU:** NVIDIA GPU optional (for faster inference)

## Installation Steps

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/monikai.git
cd monikai
```

### 2. Backend Setup

#### Create Python Virtual Environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

#### Install Python Dependencies

```bash
pip install -r requirements.txt
```

Key dependencies:
- FastAPI & Uvicorn - Web server
- Socket.IO - Real-time communication
- Google Gemini API - AI engine
- Playwright - Web automation
- Python-kasa - Smart home
- Mafic - Spotify integration

### 3. Frontend Setup

#### Install Node Dependencies

```bash
npm install
```

### 4. Configuration

#### Create `.env` file in project root

```bash
# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here

# Spotify (optional)
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8000/spotify/callback

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_bot_token

# Minecraft (optional)
MINECRAFT_SERVER=localhost:25565
MINECRAFT_USERNAME=MonikAI

# Backend
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# Frontend
FRONTEND_PORT=5173

# Debug
DEBUG=1
```

#### Obtain API Keys

**Google Gemini API:**
1. Go to [Google AI Studio](https://aistudio.google.com)
2. Sign in with Google account
3. Click "Get API key"
4. Copy key to `.env` file

**Spotify (Optional):**
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create new app
3. Accept terms
4. Copy Client ID and Secret to `.env`

**Telegram (Optional):**
1. Chat with @BotFather on Telegram
2. Create new bot with `/newbot`
3. Copy token to `.env`

### 5. Initialize Data Directories

```bash
# Windows
mkdir data\sessions
mkdir data\user_memory
mkdir data\memory
mkdir data\workspace

# macOS / Linux
mkdir -p data/{sessions,user_memory,memory,workspace}
```

### 6. Start Backend

Open terminal in project root:

```bash
# Activate venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Start backend
python -m uvicorn backend.core.server:app --reload --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 7. Start Frontend (New Terminal)

```bash
npm run dev
```

Expected output:
```
VITE v7.3.0  ready in XXX ms

➜  Local:   http://localhost:5173/
➜  press h to show help
```

### 8. Access Application

- **Web:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs (Swagger UI)

---

## First Launch

### Onboarding Flow

1. **Welcome Screen** - Introduction to MonikAI
2. **Name** - Enter your name
3. **Preferences** - Select personality traits
4. **Timezone** - Set your timezone
5. **Interests** - Choose interests
6. **Language** - Select language
7. **Confirmation** - Review and start

After onboarding, profile saved to `data/user_memory/profile.json`

### First Conversation

```
You: "Hi Monika"
Monika: "Hi! Nice to meet you :)"
```

Congratulations! System is working.

---

## Minecraft Bot Setup (Optional)

### Prerequisites

- Java 8+ installed
- Minecraft server running
- Server reachable from your machine

### Steps

1. Install Node dependencies:
   ```bash
   cd minecraft-bot
   npm install mineflayer
   ```

2. Update `.env`:
   ```
   MINECRAFT_SERVER=your.server.ip:25565
   MINECRAFT_USERNAME=MonikAI
   MINECRAFT_PASSWORD=password  # If using authenticated server
   ```

3. Test connection:
   ```bash
   node minecraft-bot/index.js --test
   ```

---

## Spotify Integration Setup (Optional)

### Steps

1. Set Spotify credentials in `.env` (see Configuration section)
2. Backend will automatically start OAuth flow
3. Click "Connect Spotify" in app
4. Approve permissions
5. Token saved to `data/spotify_tokens.json`

---

## Docker Setup (Alternative)

### Build Docker Image

```bash
docker build -t monikai .
```

### Run Container

```bash
docker run -p 8000:8000 -p 5173:5173 \
  -e GEMINI_API_KEY=your_key \
  -v $(pwd)/data:/app/data \
  monikai
```

---

## Troubleshooting Setup

### Port Already in Use

**Error:** `Address already in use :8000`

**Solution:**
```bash
# Find process using port 8000
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# macOS / Linux
lsof -i :8000
kill -9 <PID>
```

### Python Module Not Found

**Error:** `ModuleNotFoundError: No module named 'fastapi'`

**Solution:**
```bash
# Ensure venv activated
pip install -r requirements.txt
```

### Gemini API Key Invalid

**Error:** `Invalid API key provided`

**Solution:**
1. Get new key from [Google AI Studio](https://aistudio.google.com)
2. Update `.env` file
3. Restart backend

### Frontend Can't Connect to Backend

**Error:** Connection timeout when trying to send message

**Solution:**
1. Ensure backend running (`http://localhost:8000` accessible)
2. Check CORS configuration
3. Restart both frontend and backend

---

## Development Setup

See [Development Guide](./Development.md) for development environment setup.

---

## Docker Compose

For easy multi-container setup:

```yaml
version: '3.8'
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    volumes:
      - ./data:/app/data
      
  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    depends_on:
      - backend
```

Run with:
```bash
docker-compose up
```

---

**Next Read:** [Development Guide](./Development.md) | [Troubleshooting](./Troubleshooting.md)
