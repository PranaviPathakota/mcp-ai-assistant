# Architecture

## Overview

The AI Assistant is built on the **Model Context Protocol (MCP)** — an open standard that lets AI models communicate with external tools and data sources through a unified interface.

```
┌─────────────────────────────────────────────────────────────┐
│                        main_app.py                          │
│                   (AIAssistant + MCPClient)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │  JSON-RPC over stdio
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼────────┐
   │ filesystem  │  │  duckduckgo │  │   mcpizza    │
   │ MCP server  │  │ MCP server  │  │  MCP server  │
   └─────────────┘  └─────────────┘  └──────────────┘
          │
   ┌──────▼──────┐  ┌─────────────┐  ┌─────────────┐
   │   gmail     │  │  calendar   │  │  playwright  │
   │ MCP server  │  │ MCP server  │  │ MCP server   │
   └─────────────┘  └─────────────┘  └─────────────┘
```

## Components

### `main_app.py` — Central Orchestrator

The `AIAssistant` class is the core of the system. It:

1. **Spawns MCP servers** as subprocesses
2. **Communicates** with each server using JSON-RPC 2.0 over stdin/stdout
3. **Routes queries** to the appropriate tool based on user intent
4. **Classifies privacy** to decide whether to use local or cloud AI

The `MCPClient` class wraps each server subprocess and handles:
- MCP handshake (initialize / capabilities negotiation)
- `tools/list` to discover available tools
- `tools/call` to invoke specific tools

### Privacy Routing

Queries are classified into three levels before being processed:

| Level | Examples | Routing |
|-------|----------|---------|
| `SENSITIVE` | passwords, SSN, medical | Local Ollama only |
| `SEMI_PRIVATE` | meetings, schedules | Local preferred |
| `PUBLIC` | web search, general Q&A | Cloud OK (Gemini) |

### MCP Servers

| Server | Type | Purpose |
|--------|------|---------|
| `filesystem` | Node.js (TypeScript) | Read/write local files |
| `duckduckgo` | Python (`mcp_duckduckgo`) | Web search |
| `gmail` | Node.js (`npx`) | Email management |
| `calendar` | Node.js (`npx`) | Google Calendar |
| `playwright` | Node.js (`npx`) | Browser automation |
| `mcpizza` | Python (local) | Domino's pizza ordering |

### PDF Q&A Pipeline

```
User query
    │
    ▼
PDFExtractor  ──► PyPDF2 ──► raw text
    │
    ▼
PDFQAHandler  ──► Gemini API (gemini-2.5-flash)
    │
    ▼
Answer with document citations
```

PDF Q&A uses Google Gemini (flash) because it has a large context window suitable for long documents.

### Browser Automation (Pizza Ordering)

When ordered via natural language, the assistant:
1. Uses **DuckDuckGo MCP** to find pizza restaurant websites
2. Opens the site using **Playwright MCP** (`browser_navigate`)
3. Autonomously clicks order buttons (`browser_click`)
4. Fills forms (`browser_fill`) using fallback selector patterns
5. Stops before payment (safety feature)

Alternatively, the **MCPizza server** communicates directly with the Domino's API via `pizzapi`, bypassing browser automation entirely.

## Key Design Decisions

- **MCP over direct API calls**: Decouples AI logic from tool implementation; servers can be swapped or extended independently
- **Subprocess-per-server**: Each MCP server runs isolated; crashes don't affect the main loop
- **Local LLM fallback**: Ollama (`llama3.1:8b`) is used when privacy requirements prevent cloud routing
- **Gemini for documents**: Used only for PDF Q&A where the large context window matters; Gemini is not used for private data
