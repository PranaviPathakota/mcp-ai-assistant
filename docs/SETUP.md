# Setup & Installation

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.9+ | For main app and MCP servers |
| Node.js | 18+ | For npx-based MCP servers |
| npm / npx | 9+ | Comes with Node.js |
| Ollama | latest | Local LLM |

---

## 1. Clone & Install Python Dependencies

```bash
git clone <your-repo-url>
cd ai-assistant-clean

pip install -r requirements.txt
pip install -r mcpizza/requirements.txt
```

---

## 2. Install Ollama and Pull Model

```bash
# Install Ollama (macOS)
brew install ollama

# Start the Ollama service
ollama serve

# In a new terminal tab, pull the model
ollama pull llama3.1:8b
```

> If you see "address already in use" when running `ollama serve`, Ollama is already running — skip this step.

---

## 3. Set Up Gmail & Calendar (Optional)

Gmail and Calendar require a one-time Google OAuth setup. Skip this if you don't need email/calendar features.

### 3a. Create Google OAuth credentials

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com)
2. Create or select a project
3. **APIs & Services → Library** → Enable **Gmail API**
4. **APIs & Services → Library** → Enable **Google Calendar API**
5. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
6. Application type: **Desktop app** → Create
7. Download the JSON file → save it as `gcp-oauth.keys.json`

### 3b. Place credentials in the expected location

```bash
mkdir -p ~/.gmail-mcp
mv ~/Downloads/client_secret_*.json ~/.gmail-mcp/gcp-oauth.keys.json
```

### 3c. Authenticate Gmail (run once)

```bash
npx @gongrzhe/server-gmail-autoauth-mcp auth
```

A browser window opens — sign in with Google and grant the requested permissions:
- Read, compose, and send emails
- See, edit, create, or change email settings and filters

### 3d. Authenticate Calendar (run once)

```bash
npx @gongrzhe/server-calendar-autoauth-mcp auth
```

Same OAuth flow — sign in and grant calendar access.

> Tokens are saved to `~/.gmail-mcp/` automatically. You will not need to re-authenticate unless the token expires.

---

## 4. Set Up Gemini API (Optional — for PDF Q&A)

1. Get a free API key at [https://ai.google.dev](https://ai.google.dev)
2. Export it in your shell:

```bash
export GEMINI_API_KEY="your-key-here"
```

---

## 5. Run the Assistant

```bash
# Basic (Ollama + web search + email + calendar + pizza)
python main_app.py

# With PDF Q&A enabled
GEMINI_API_KEY=your-key-here python main_app.py
```

---

## What works without any setup

| Feature | Requires |
|---------|----------|
| General chat | Ollama running |
| Web search | Nothing extra |
| Read/write files | Nothing extra |
| Pizza ordering | Internet connection |
| PDF Q&A | `GEMINI_API_KEY` |
| Gmail | Steps 3a–3c above |
| Google Calendar | Steps 3a–3d above |

---

## Troubleshooting

**Ollama connection error** — Run `ollama serve` in a separate terminal

**MCP server not starting** — Check Node.js is installed: `node --version` and `npx --version`

**Gmail/Calendar `invalid_grant`** — Re-run the auth commands in Step 3c and 3d

**Gmail/Calendar `No access token`** — The `gcp-oauth.keys.json` file is missing or in the wrong location; check `~/.gmail-mcp/gcp-oauth.keys.json` exists

**MCPizza errors** — The Domino's API can be unreliable; try a different US ZIP code
