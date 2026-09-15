# AI Assistant with MCP Tool Integration

A privacy-aware AI assistant built on the **Model Context Protocol (MCP)**. It connects a local LLM (Ollama) and Google Gemini to a suite of tools — filesystem access, web search, email, calendar, browser automation, and pizza ordering — all through a unified MCP interface.

Built for CSCE 689: Programming LLMs (HW3).

---

## Features

| Capability | Tool Used |
|------------|-----------|
| Read/write local files | Filesystem MCP server |
| Web search | DuckDuckGo MCP server |
| Email management | Gmail MCP server (auto-auth) |
| Calendar scheduling | Google Calendar MCP server |
| PDF Q&A | Gemini API (gemini-2.5-flash) |
| Browser automation | Playwright MCP server |
| Pizza ordering (browser) | Playwright + DuckDuckGo |
| Pizza ordering (API) | MCPizza + Domino's API |

Privacy routing ensures sensitive queries stay local (Ollama), while public queries can use cloud AI (Gemini).

---

## Project Structure

```
mcp-ai-assistant/
├── main_app.py          # Main entry point — AIAssistant + MCPClient
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
│
├── pdf/                 # PDF utilities
│   ├── extractor.py     # PDF text extraction (PyPDF2)
│   ├── qa_handler.py    # PDF Q&A using Gemini API
│   └── docs/            # Sample PDFs for Q&A demo
│
├── mcpizza/             # MCP server for Domino's pizza ordering
│   ├── mcpizza/
│   │   ├── server.py    # MCP server implementation
│   │   └── http_server.py
│   ├── pyproject.toml
│   └── requirements.txt
│
├── servers/             # MCP server source (TypeScript/Python)
│   └── src/
│       ├── filesystem/  # File read/write/search
│       ├── fetch/       # HTTP fetch
│       ├── memory/      # Persistent memory
│       ├── git/         # Git operations
│       ├── time/        # Current time/timezone
│       └── everything/  # Test/demo server (all transports)
│
├── tests/               # Test scripts
└── docs/
    ├── ARCHITECTURE.md  # System design and MCP communication
    ├── SETUP.md         # Detailed installation guide
    └── PIZZA_ORDERING.md # Pizza ordering docs (both modes)
```

---

## Quick Start

### 1. Prerequisites

- Python 3.9+, Node.js 18+, npm
- [Ollama](https://ollama.com) with `llama3.1:8b`

### 2. Install Dependencies

```bash
pip install -r requirements.txt
pip install -r mcpizza/requirements.txt
```

### 3. Start Ollama

```bash
ollama serve &
ollama pull llama3.1:8b
```

### 4. Set up environment variables

```bash
cp .env.example .env
# open .env and add your Gemini API key (optional, for PDF Q&A)
```

### 5. Run

```bash
python main_app.py
```

Full setup instructions: [docs/SETUP.md](docs/SETUP.md)

---

## How It Works

The `AIAssistant` spawns each MCP server as a subprocess and communicates over **JSON-RPC 2.0 via stdin/stdout**. When a user query arrives:

1. Privacy level is classified (sensitive / semi-private / public)
2. The appropriate LLM handles the query (Ollama locally, or Gemini for documents)
3. Tool calls are dispatched to the relevant MCP server
4. Results are returned to the user

```
User → AIAssistant → MCPClient → [MCP Server subprocess]
                   ↘ Ollama (local LLM, for sensitive queries)
                   ↘ Gemini API (for PDF Q&A)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

---

## Usage Examples

### Web Search

```
You: What is the latest news about large language models?

Searching DuckDuckGo for 'large language models news'...
[Results from web search displayed]
```

### PDF Q&A

```
You: load pdf ~/Documents/paper.pdf
You: What is the main contribution of this paper?

[Gemini reads the PDF and answers based on its content]
```

### Pizza Ordering

```
You: order pizza

Location: College Station, TX
[DuckDuckGo finds nearby pizza places]

Which restaurant? 1

Address: 123 Main St, Apt 4
Phone: 555-123-4567
Name: Jane Doe

[Playwright opens the site, fills the form, stops before payment]
```

See [docs/PIZZA_ORDERING.md](docs/PIZZA_ORDERING.md) for the Domino's API ordering mode.

---

## MCP Servers

| Server | Type | How it runs |
|--------|------|-------------|
| `filesystem` | TypeScript | `npx @modelcontextprotocol/server-filesystem` |
| `duckduckgo` | Python | `python -m mcp_duckduckgo.main` |
| `gmail` | Node.js | `npx @gongrzhe/server-gmail-autoauth-mcp` |
| `calendar` | Node.js | `npx @gongrzhe/server-calendar-autoauth-mcp` |
| `playwright` | Node.js | `npx @playwright/mcp@latest` |
| `mcpizza` | Python | `python -m mcpizza.server` |

---

## Dependencies

**Python** (`requirements.txt`):
- `requests` — HTTP calls to Ollama
- `google-generativeai` — Gemini API for PDF Q&A
- `PyPDF2` — PDF text extraction
- `beautifulsoup4` — HTML parsing
- `python-dotenv` — loads API keys from `.env`

**MCPizza** (`mcpizza/requirements.txt`):
- `pizzapi` — Unofficial Domino's API client
- `mcp` — MCP server framework

**Node.js servers**: Run via `npx` — no build step required. Source in `servers/src/` for reference.

---

## License

MIT
