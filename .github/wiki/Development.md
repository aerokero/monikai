# Development Guide

Guide for contributing to MonikAI development.

## Development Environment

### Prerequisites

- Same as [Setup & Installation](./Setup.md)
- Git
- VS Code or IDE of choice
- Basic Python and React knowledge

### Dev Setup

```bash
# Clone and setup
git clone https://github.com/yourusername/monikai.git
cd monikai
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
npm install
```

### Run Dev Servers

**Terminal 1 - Backend:**
```bash
.venv\Scripts\activate
python -m uvicorn backend.core.server:app --reload
```

**Terminal 2 - Frontend:**
```bash
npm run dev
```

Both support hot-reload on code changes.

---

## Project Structure

```
monikai/
├── backend/            # Python backend
│   ├── ai/            # AI engines
│   ├── core/          # Server + main loop
│   ├── agents/        # External integrations
│   ├── tools/         # Tools for Gemini
│   └── data/          # User data
├── src/               # React frontend
│   ├── components/    # React components
│   ├── contexts/      # Context providers
│   ├── hooks/         # Custom hooks
│   └── styles/        # CSS
├── scripts/           # Utility scripts
├── skills/            # Integration skills
└── package.json, requirements.txt, etc.
```

---

## Making Changes

### Backend Changes

1. **Edit Python File**
   ```python
   # backend/ai/personality.py
   async def observe_message(self, text: str):
       # Your changes here
   ```

2. **Backend reloads automatically** (with `--reload` flag)

3. **Test changes:**
   ```bash
   python backend/test_personality_state.py
   ```

### Frontend Changes

1. **Edit React Component**
   ```jsx
   // src/components/ChatModule.jsx
   export function ChatModule() {
       // Your changes here
   }
   ```

2. **Frontend reloads automatically** in browser (Vite HMR)

3. **Test in browser at** `http://localhost:5173`

---

## Testing

### Backend Tests

```bash
# Run all tests
python -m pytest backend/tests/

# Run specific test file
python -m pytest backend/test_personality_state.py

# Run with verbose output
python -m pytest backend/tests/ -v
```

### Frontend Tests

```bash
# Run tests
npm test

# Watch mode
npm test -- --watch
```

### Manual Testing

1. Start both servers
2. Open http://localhost:5173
3. Send messages
4. Check Console for errors
5. Backend logs show request details

---

## Code Style

### Python

Follow PEP 8:
- Use 4 spaces for indentation
- Max line length: 88 characters (Black formatter)
- Type hints recommended

```python
# Good
async def observe_message(self, text: str, sender: str) -> dict:
    signals = self.analyze(text)
    return signals

# Bad
async def observe_message(self,text,sender):
    signals=self.analyze(text)
    return signals
```

**Auto-format with Black:**
```bash
pip install black
black backend/
```

### React/JavaScript

Use Prettier:
```bash
npm install prettier
npm prettier -- --write src/
```

Style guide:
- Use functional components
- Use hooks instead of classes
- Use camelCase for variables/functions
- Use PascalCase for components

```jsx
// Good
export function ChatModule() {
  const [messages, setMessages] = useState([]);
  return <div>{messages.map(...)}</div>;
}

// Bad
class ChatModule extends Component {
  state = { messages: [] }
  render() { ... }
}
```

---

## Adding Features

### Adding New Backend Module

1. **Create file** in `backend/ai/new_module.py`

```python
class NewModule:
    def __init__(self):
        self.state = {}
    
    async def initialize(self):
        pass
```

2. **Register in** `backend/core/server.py`

```python
from backend.ai.new_module import NewModule

@app.on_event("startup")
async def startup():
    global new_module
    new_module = NewModule()
```

3. **Add endpoint**

```python
@app.get("/api/new-module/state")
async def get_new_module_state():
    return new_module.state
```

4. **Test endpoint**

```bash
curl http://localhost:8000/api/new-module/state
```

### Adding New Frontend Component

1. **Create component** in `src/components/NewComponent.jsx`

```jsx
export function NewComponent() {
  const { socket } = useContext(RealtimeContext);
  
  useEffect(() => {
    socket.on('new_event', (data) => {
      console.log(data);
    });
  }, [socket]);
  
  return <div>New Component</div>;
}
```

2. **Add to Layout**

```jsx
// src/layout/Shell.jsx
import { NewComponent } from '../components/NewComponent';

export function Shell() {
  return (
    <div>
      <ChatModule />
      <NewComponent />  {/* Add here */}
    </div>
  );
}
```

3. **Test in browser**

---

## Debugging

### Python Debugging

**Using print statements:**
```python
print(f"Debug: {value}")
```

**Using pdb:**
```python
import pdb; pdb.set_trace()  # Debugger will stop here
```

**Enable DEBUG mode:**
```bash
DEBUG=1 python -m uvicorn backend.core.server:app --reload
```

### React Debugging

**Using console:**
```jsx
console.log("Debug:", value);
console.error("Error:", error);
```

**Using React DevTools:**
Install [React DevTools](https://chrome.google.com/webstore/detail/react-developer-tools/) browser extension

**Using Debugger:**
```jsx
debugger;  // Stops here if DevTools open
```

### Network Debugging

**Monitor WebSocket in Chrome DevTools:**
1. Open DevTools (F12)
2. Go to Network tab
3. Filter by WS (WebSocket)
4. Click on connection to see messages

---

## Git Workflow

### Create Branch

```bash
git checkout -b feature/my-feature
# or
git checkout -b bugfix/issue-123
```

### Make Changes

```bash
git add .
git commit -m "Add my feature"
```

**Commit message format:**
- `feat: Add new feature`
- `fix: Fix bug in module`
- `docs: Update documentation`
- `refactor: Improve code structure`
- `test: Add new tests`

### Push and Create PR

```bash
git push origin feature/my-feature
```

Then create Pull Request on GitHub.

---

## Documentation

### Adding Code Comments

```python
# Bad - Obvious
x = x + 1  # Increment x

# Good - Explains why
# Add XP to account for message engagement
metrics.add_xp(source='message', amount=10)
```

### Updating Wiki

Edit markdown files in `.github/wiki/`

---

## Performance Tips

### Python Backend

```python
# Use async for I/O operations
async def fetch_data():
    result = await some_async_operation()
    
# Cache expensive operations
@functools.lru_cache(maxsize=128)
def expensive_calculation(x):
    return x ** 2
```

### React Frontend

```jsx
// Memoize components
const ExpensiveComponent = React.memo(function Component() {
  return <div>...</div>;
});

// Use useMemo for expensive calculations
const memoizedValue = useMemo(() => expensive(a, b), [a, b]);

// Use useCallback for stable function references
const memoizedCallback = useCallback((x) => x + 1, []);
```

---

## Common Issues

### "Module not found" error

```bash
# Reinstall dependencies
pip install -r requirements.txt
npm install
```

### Port conflicts

```bash
# Kill process using port 8000
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Hot-reload not working

```bash
# Restart dev servers
# Ctrl+C on both terminals
# Run again
python -m uvicorn ...
npm run dev
```

---

## Contributing Guidelines

1. Fork repository
2. Create feature branch
3. Make changes with tests
4. Update documentation
5. Create Pull Request
6. Wait for code review

---

**Next Read:** [Troubleshooting](./Troubleshooting.md) | [Architecture](./Architecture.md)
