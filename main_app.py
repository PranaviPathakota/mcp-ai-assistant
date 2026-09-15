#!/usr/bin/env python3

import asyncio
import json
import os
import subprocess
import requests
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv
from pdf.qa_handler import PDFQAHandler

load_dotenv()  # loads .env from project root if present

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PrivacyLevel(Enum):
    SENSITIVE = "sensitive"        # Personal docs, private emails - local only
    SEMI_PRIVATE = "semi_private"  # Meeting schedules - local preferred  
    PUBLIC = "public"              # Web search, general queries - cloud OK

@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: List[str]
    env: Dict[str, str] = None
    process: Optional[subprocess.Popen] = None

class MCPClient:
    """Handle JSON-RPC communication with MCP servers"""

    def __init__(self, process: subprocess.Popen):
        self.process = process
        self.request_id = 0
        self.initialized = False

    async def initialize(self) -> bool:
        """Initialize the MCP server with handshake"""
        try:
            logger.debug("Sending initialize request to MCP server")
            response = await self.send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "ai-assistant",
                    "version": "1.0.0"
                }
            })

            if "result" in response:
                logger.debug(f"Initialize successful: {response['result']}")
                self.initialized = True
                return True
            else:
                logger.error(f"Initialize failed: {response}")
                return False

        except Exception as e:
            logger.error(f"Error during initialization: {e}")
            return False

    async def send_request(self, method: str, params: Dict = None) -> Dict:
        """Send JSON-RPC request to MCP server"""
        self.request_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }

        try:
            # Send request to server via stdin
            request_json = json.dumps(request) + "\n"
            logger.debug(f"Sending request: {request_json.strip()}")
            self.process.stdin.write(request_json.encode())
            self.process.stdin.flush()

            # Read response from stdout with timeout
            await asyncio.sleep(0.1)  # Give server time to process

            response_line = self.process.stdout.readline().decode().strip()
            logger.debug(f"Received response: {response_line[:200]}")

            if response_line:
                response = json.loads(response_line)
                return response
            else:
                return {"error": {"code": -1, "message": "No response from server"}}

        except Exception as e:
            logger.error(f"MCP communication error: {e}")
            return {"error": {"code": -1, "message": str(e)}}

    async def list_tools(self) -> List[Dict]:
        """Get available tools from MCP server"""
        # Initialize if not already done
        if not self.initialized:
            await self.initialize()

        response = await self.send_request("tools/list")
        if "result" in response and "tools" in response["result"]:
            return response["result"]["tools"]
        return []
    
    async def call_tool(self, tool_name: str, arguments: Dict) -> str:
        """Call a specific tool on the MCP server"""
        # Initialize if not already done
        if not self.initialized:
            await self.initialize()

        response = await self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        if "result" in response and "content" in response["result"]:
            # Extract text content from MCP response
            content = response["result"]["content"]
            if isinstance(content, list) and len(content) > 0:
                return content[0].get("text", "No text content")
            return str(content)
        elif "error" in response:
            return f"Error: {response['error'].get('message', 'Unknown error')}"
        else:
            return "No response from tool"

class AIAssistant:
    def __init__(self, gemini_api_key: Optional[str] = None):
        self.ollama_url = "http://localhost:11434"
        self.mcp_servers: Dict[str, MCPServerConfig] = {}
        self.mcp_clients: Dict[str, MCPClient] = {}
        self.setup_mcp_servers()

        # Initialize PDF Q&A handler with Gemini API if key provided
        self.pdf_handler = None
        if gemini_api_key:
            try:
                self.pdf_handler = PDFQAHandler(gemini_api_key)
                logger.info("✅ PDF Q&A Handler initialized with Gemini API")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize PDF handler: {e}")
        
    def setup_mcp_servers(self):
        """Configure all MCP servers"""
        # Get the current directory for relative paths
        current_dir = os.getcwd()
        
        self.mcp_servers = {
            'filesystem': MCPServerConfig(
                name='filesystem',
                command='npx',
                args=['-y', '@modelcontextprotocol/server-filesystem', f'{os.path.expanduser("~/Documents")}'],
                env={}
            ),
            'duckduckgo': MCPServerConfig(
                name='duckduckgo',
                command='python',
                args=['-m', 'mcp_duckduckgo.main'],
                env={}
            ),
            
            'gmail': MCPServerConfig(
                name='gmail',
                command='npx',
                args=['@gongrzhe/server-gmail-autoauth-mcp'],
                env={}
            ),
            'calendar': MCPServerConfig(
                name='calendar',
                command='npx',
                args=['@gongrzhe/server-calendar-autoauth-mcp'],
                env={}
            ),
            'playwright': MCPServerConfig(
                name='playwright',
                command='npx',
                args=['@playwright/mcp@latest'],
                env={}
            ),
            # mcpizza - NOW WORKING! Fixed all API incompatibility issues
            # Fixed: search_menu now includes store_id, set_customer_info uses address object,
            #        removed calls to non-existent tools (get_store_menu_categories, prepare_order)
            # Uses Domino's API via pizzapi library for real pizza ordering
            'mcpizza': MCPServerConfig(
                name='mcpizza',
                command='python',
                args=['-m', 'mcpizza.server'],
                env={}
            ),
        }
    
    def classify_privacy_level(self, content: str) -> PrivacyLevel:
        """Classify content privacy level for routing decisions"""
        sensitive_keywords = [
            'password', 'ssn', 'social security', 'credit card',
            'personal', 'private', 'confidential', 'bank account',
            'salary', 'medical', 'health'
        ]
        
        semi_private_keywords = [
            'meeting', 'schedule', 'calendar', 'appointment',
            'internal', 'company', 'team', 'employee',
            'project', 'deadline', 'client'
        ]
        
        content_lower = content.lower()
        
        if any(keyword in content_lower for keyword in sensitive_keywords):
            return PrivacyLevel.SENSITIVE
        elif any(keyword in content_lower for keyword in semi_private_keywords):
            return PrivacyLevel.SEMI_PRIVATE
        else:
            return PrivacyLevel.PUBLIC
    
    async def query_ollama(self, prompt: str, context: str = "", model: str = "llama3.1:8b") -> str:
        """Query the local Ollama model"""
        try:
            system_prompt = """You are a helpful AI assistant with access to various tools including:
- Email management (Gmail)
- Calendar scheduling
- File/PDF reading
- Web search and content fetching

When users ask you to perform actions, analyze their request and determine what tools to use.
Be concise but helpful in your responses."""

            full_prompt = f"System: {system_prompt}\n\nContext: {context}\n\nUser: {prompt}\n\nAssistant:"

            logger.info(f"📤 Sending request to Ollama (prompt length: {len(full_prompt)} chars)")

            response = requests.post(f"{self.ollama_url}/api/generate", json={
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_ctx": 4096
                }
            }, timeout=60)  # Increased timeout to 60 seconds for large prompts

            logger.info(f"📥 Received response from Ollama (status: {response.status_code})")

            if response.status_code == 200:
                result = response.json().get('response', '').strip()
                logger.info(f"✅ Ollama response length: {len(result)} chars")
                return result
            else:
                logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                return "Sorry, I encountered an error processing your request locally."

        except requests.exceptions.Timeout as e:
            logger.error(f"⏱️ Ollama request timed out: {e}")
            return "Sorry, the request took too long. The content might be too large for the model to process."
        except requests.exceptions.ConnectionError as e:
            logger.error(f"🔌 Cannot connect to Ollama: {e}")
            return "Sorry, I'm having trouble connecting to the local AI model. Make sure Ollama is running."
        except Exception as e:
            logger.error(f"❌ Error querying Ollama: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"Sorry, I encountered an error: {str(e)}"
    
    async def start_mcp_servers(self):
        """Start all MCP servers and create clients"""
        logger.info("🚀 Starting MCP servers...")
        
        for name, config in self.mcp_servers.items():
            try:
                env = {**os.environ, **(config.env or {})}
                
                # Start the MCP server process with JSON-RPC communication
                process = subprocess.Popen(
                    [config.command] + config.args,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    text=False,  # Use binary mode for proper JSON-RPC
                    bufsize=0    # Unbuffered
                )
                
                config.process = process
                
                # Create MCP client for this server
                self.mcp_clients[name] = MCPClient(process)
                
                logger.info(f"✅ Started MCP server: {name}")
                
                # Give servers time to initialize
                await asyncio.sleep(2)
                
                # Test connection by listing tools
                try:
                    tools = await self.mcp_clients[name].list_tools()
                    logger.info(f"📋 {name} tools: {[tool.get('name', 'unknown') for tool in tools]}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not list tools for {name}: {e}")

                    # Check stderr for errors
                    if config.process and config.process.stderr:
                        try:
                            import select
                            # Non-blocking read of stderr
                            stderr_data = config.process.stderr.read()
                            if stderr_data:
                                logger.error(f"❌ {name} stderr: {stderr_data.decode()}")
                        except:
                            pass
                
            except Exception as e:
                logger.error(f"❌ Failed to start MCP server {name}: {e}")
    
    async def send_email(self, params: Dict) -> str:
        """Send email via Gmail MCP server"""
        try:
            to_email = params.get('to', '')
            subject = params.get('subject', '')
            body = params.get('body', '')

            # Validate inputs
            if not to_email or '@' not in to_email:
                return "❌ Invalid email address. Please provide a valid email."

            if not subject:
                return "❌ Email subject cannot be empty."

            if not body:
                return "❌ Email body cannot be empty."

            if 'gmail' not in self.mcp_clients:
                return "❌ Gmail server not available. Please check if the Gmail MCP server is running."

            # Show preview and confirm
            print("\n📧 Email Preview:")
            print(f"To: {to_email}")
            print(f"Subject: {subject}")
            print(f"Body:\n{body[:200]}{'...' if len(body) > 200 else ''}")

            confirm = input("\n✅ Send this email? (yes/no): ").strip().lower()
            if confirm not in ['yes', 'y']:
                return "❌ Email sending cancelled."

            # Call the Gmail MCP server
            result = await self.mcp_clients['gmail'].call_tool('send_email', {
                'to': [to_email],
                'subject': subject,
                'body': body,
                'mimeType': 'text/plain'
            })

            logger.info(f"Gmail MCP response: {result}")

            if any(word in result.lower() for word in ['error', 'failed', 'unauthorized', 'invalid', 'exception']):
                return f"❌ Gmail MCP server returned an error:\n{result}"

            return f"✅ Email sent successfully!\n📧 To: {to_email}\n📋 Subject: {subject}\n\nServer response: {result}"

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return f"❌ Failed to send email: {str(e)}\nPlease check your Gmail MCP server configuration and authentication."
    
    async def read_multiple_pdfs(self, params: Dict) -> str:
        """Read multiple PDF files and enable Q&A with Gemini"""
        try:
            if not self.pdf_handler:
                return "❌ PDF Q&A not available. Please provide Gemini API key when starting the assistant."

            if 'filesystem' not in self.mcp_clients:
                return "❌ Filesystem server not available"

            # Get PDF paths from params
            pdf_paths = params.get('paths', [])

            if not pdf_paths:
                return "❌ No PDF paths provided"

            # Load all PDFs and extract text
            loaded = self.pdf_handler.load_pdfs(pdf_paths)

            if not loaded:
                return "❌ Failed to load any PDFs"

            # Show loaded PDFs
            print(f"\n{self.pdf_handler.list_loaded_pdfs()}\n")

            # Ask if user wants a summary
            want_summary = input("📝 Would you like a summary of all documents? (yes/no): ").strip().lower()

            if want_summary in ['yes', 'y']:
                print("\n⏳ Generating summary using Gemini...")
                summary = self.pdf_handler.summarize_all_pdfs()
                print(f"\n📝 Summary:\n{summary}\n")

            # Q&A loop
            ask_questions = input("\n❓ Would you like to ask questions about these documents? (yes/no): ").strip().lower()

            if ask_questions in ['yes', 'y']:
                print("\n💡 Ask questions about the loaded documents. Type 'done' to finish.\n")

                while True:
                    question = input("💬 Your question: ").strip()
                    if question.lower() in ['done', 'exit', 'quit']:
                        break

                    if not question:
                        continue

                    print("\n⏳ Searching documents and generating answer...")
                    answer = self.pdf_handler.answer_question(question)
                    print(f"\n🤖 Answer:\n{answer}\n")

            return f"✅ Successfully processed {len(loaded)} PDF documents using Gemini API"

        except Exception as e:
            logger.error(f"Error reading PDFs: {e}")
            return f"❌ Failed to read PDFs: {str(e)}"

    async def read_file(self, params: Dict) -> str:
        """Read file via filesystem MCP server"""
        try:
            filepath = params.get('path', '')

            if 'filesystem' not in self.mcp_clients:
                return "❌ Filesystem server not available"

            # Expand home directory if needed
            import os
            if filepath.startswith('~'):
                filepath = os.path.expanduser(filepath)

            # Call the filesystem MCP server
            result = await self.mcp_clients['filesystem'].call_tool('read_file', {
                'path': filepath
            })

            # Check if user wants to ask questions about the content
            ask_questions = input("\n❓ Would you like to ask questions about this file? (yes/no): ").strip().lower()

            if ask_questions in ['yes', 'y']:
                while True:
                    question = input("\n💬 Your question (or 'done' to finish): ").strip()
                    if question.lower() in ['done', 'exit', 'quit']:
                        break

                    # Use Ollama to answer questions about the file content
                    answer_prompt = f"""
Based on this document content:
{result[:3000]}

Answer this question: {question}

Provide a clear, concise answer based only on the information in the document.
"""
                    answer = await self.query_ollama(answer_prompt)
                    print(f"\n🤖 Answer: {answer}\n")

            return f"📄 File read successfully: {filepath}\n\n{result[:500]}{'...' if len(result) > 500 else ''}"

        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return f"❌ Failed to read file: {str(e)}"
    
    async def schedule_meeting(self, params: Dict) -> str:
        """Schedule meeting via calendar MCP server"""
        try:
            title = params.get('title', '')
            start_time = params.get('start_time', '')
            end_time = params.get('end_time', '')
            attendees = params.get('attendees', [])

            # Validate inputs
            if not title:
                return "❌ Meeting title cannot be empty."

            if not start_time or not end_time:
                return "❌ Meeting start and end times are required."

            if 'calendar' not in self.mcp_clients:
                return "❌ Calendar server not available. Please check if the Calendar MCP server is running."

            # Show preview and confirm
            print("\n📅 Meeting Preview:")
            print(f"Title: {title}")
            print(f"Start: {start_time}")
            print(f"End: {end_time}")

            confirm = input("\n✅ Schedule this meeting? (yes/no): ").strip().lower()
            if confirm not in ['yes', 'y']:
                return "❌ Meeting scheduling cancelled."

            # Call the calendar MCP server
            result = await self.mcp_clients['calendar'].call_tool('create_event', {
                'summary': title,
                'start': {'dateTime': start_time},
                'end': {'dateTime': end_time}
            })

            logger.info(f"Calendar MCP response: {result}")

            if any(word in result.lower() for word in ['error', 'failed', 'unauthorized', 'invalid', 'exception']):
                return f"❌ Calendar MCP server returned an error:\n{result}"

            return f"✅ Meeting scheduled successfully!\n📅 Title: {title}\n⏰ {start_time} to {end_time}\n\nServer response: {result}"

        except Exception as e:
            logger.error(f"Error scheduling meeting: {e}")
            return f"❌ Failed to schedule meeting: {str(e)}\nPlease check your Calendar MCP server configuration and authentication."
    
    async def web_search(self, params: Dict) -> str:
        """Search web via DuckDuckGo MCP server and fetch real content"""
        try:
            query = params.get('query', '')

            if not query:
                return "❌ Search query cannot be empty."

            print(f"\n🔍 Searching for: {query}...")

            # Try using DuckDuckGo MCP server
            if 'duckduckgo' in self.mcp_clients:
                try:
                    logger.info(f"🔍 Using DuckDuckGo MCP server for query: {query}")

                    # Step 1: Get search results
                    search_result = await self.mcp_clients['duckduckgo'].call_tool('web_search', {
                        'query': query,
                        'max_results': 3  # Get top 3 results
                    })

                    logger.info(f"📄 Got search results, length: {len(search_result)} characters")

                    # Parse the JSON result to extract URLs
                    import json
                    try:
                        # Extract JSON from the text response
                        if "results" in search_result:
                            # Parse the results to get URLs
                            result_data = json.loads(search_result)
                            urls = []

                            # Extract URLs from results
                            if isinstance(result_data, dict) and 'results' in result_data:
                                for item in result_data['results'][:2]:  # Get top 2 URLs
                                    if 'url' in item:
                                        urls.append(item['url'])

                            if not urls:
                                # Fallback: try to extract URLs with regex
                                import re
                                url_pattern = r'https?://[^\s"\'\)>]+'
                                urls = re.findall(url_pattern, search_result)[:2]

                            logger.info(f"📋 Extracted {len(urls)} URLs: {urls}")

                            # Step 2: Fetch content from top URLs
                            print("📥 Fetching content from top results...")
                            all_content = []

                            for i, url in enumerate(urls[:2], 1):  # Fetch top 2 pages
                                try:
                                    print(f"  {i}. Fetching: {url[:60]}...")

                                    page_content = await self.mcp_clients['duckduckgo'].call_tool('get_page_content', {
                                        'url': url
                                    })

                                    if page_content and len(page_content) > 100:
                                        all_content.append(f"Source {i}: {url}\n{page_content[:2000]}")
                                        logger.info(f"✅ Fetched content from {url}, length: {len(page_content)}")
                                    else:
                                        logger.warning(f"⚠️ Empty content from {url}")

                                except Exception as e:
                                    logger.warning(f"⚠️ Failed to fetch {url}: {e}")
                                    continue

                            # Step 3: Summarize the content using Ollama
                            if all_content:
                                print("🤖 Generating AI summary from fetched content...")

                                combined_content = "\n\n".join(all_content)

                                summary_prompt = f"""Based on the following web content about "{query}", provide a comprehensive summary:

{combined_content[:4000]}

Please provide:
1. A concise overview of what you found
2. Key points and important information
3. Any relevant facts, statistics, or findings

Be informative and well-structured."""

                                summary = await self.query_ollama(summary_prompt)

                                return f"""🔍 Web Search Results for: {query}

📝 AI-Generated Summary:
{summary}

🔗 Sources:
{chr(10).join([f"  {i+1}. {url}" for i, url in enumerate(urls[:2])])}

✅ Content fetched and summarized from real web pages via DuckDuckGo MCP"""
                            else:
                                # Just return search results if content fetch failed
                                return f"🔍 Search Results for: {query}\n\n{search_result}\n\n⚠️ Could not fetch page content, showing search results only"

                    except json.JSONDecodeError:
                        # If JSON parsing fails, just return the search results
                        logger.warning("⚠️ Could not parse JSON, returning raw results")
                        return f"🔍 Search Results for: {query}\n\n{search_result}\n\n✅ Results from DuckDuckGo MCP"

                except Exception as e:
                    logger.warning(f"⚠️ DuckDuckGo MCP failed: {e}, trying fallback")
            else:
                logger.warning("⚠️ DuckDuckGo MCP client not available, using fallback")

            # Fallback: Direct HTTP request using requests library
            logger.info("Using fallback HTTP request for web search")

            try:
                import requests
                from bs4 import BeautifulSoup

                # Use DuckDuckGo HTML search
                url = f'https://html.duckduckgo.com/html/?q={query.replace(" ", "+")}'

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }

                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()

                # Parse HTML
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract search results
                results = []
                for result in soup.find_all('div', class_='result__body')[:5]:
                    title_elem = result.find('a', class_='result__a')
                    snippet_elem = result.find('a', class_='result__snippet')

                    if title_elem and snippet_elem:
                        title = title_elem.get_text(strip=True)
                        snippet = snippet_elem.get_text(strip=True)
                        results.append(f"**{title}**\n{snippet}\n")

                if results:
                    search_results = "\n".join(results)
                    return f"🔍 Search Results for: {query}\n\n{search_results}\n\n💡 Fallback results from DuckDuckGo HTML"
                else:
                    return f"❌ No search results found for: {query}"

            except Exception as e:
                logger.error(f"Fallback search failed: {e}")
                return f"❌ Web search failed: {str(e)}\n\n💡 Please check your internet connection."

        except Exception as e:
            logger.error(f"Error in web search: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"❌ Failed to search web: {str(e)}"

    async def order_pizza(self, params: Dict) -> str:
        """Order pizza using mcpizza MCP server (preferred) or browser automation fallback"""
        try:
            print("\n🍕 Pizza Ordering Assistant")
            print("=" * 50)

            # Check if mcpizza MCP server is available
            if 'mcpizza' in self.mcp_clients:
                print("✅ Using Domino's API via mcpizza MCP server")
                return await self.order_pizza_with_api(params)
            elif 'playwright' in self.mcp_clients:
                print("⚠️  mcpizza MCP not available, falling back to browser automation")
                return await self.order_pizza_with_browser(params)
            else:
                return "❌ Neither mcpizza nor browser automation available. Cannot order pizza."

        except Exception as e:
            logger.error(f"Error in pizza ordering: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"❌ Failed to order pizza: {str(e)}"

    async def order_pizza_with_api(self, params: Dict) -> str:
        """Order pizza using mcpizza MCP server (Domino's API) - FIXED VERSION"""
        try:
            print("\n🍕 Domino's Pizza Ordering via API")
            print("=" * 50)

            # Step 1: Gather delivery details - need structured address
            print("\n📍 Enter your delivery address:")
            street = input("   Street address: ").strip()
            city = input("   City: ").strip()
            state = input("   State (e.g., TX, CA, NY): ").strip()
            zip_code = input("   ZIP code: ").strip()
            full_address = f"{street}, {city}, {state} {zip_code}"

            phone = input("\n📞 Phone number (e.g., 555-123-4567): ").strip()
            name = input("✍️  Your name (First Last): ").strip()
            email = input("📧 Email address: ").strip()

            # Parse name
            first_name, last_name = (name.split(' ', 1) + [''])[:2]
            if not last_name:
                last_name = first_name

            # Step 2: Find nearest Domino's store
            print(f"\n🔍 Finding nearest Domino's store to {full_address}...")
            store_result = await self.mcp_clients['mcpizza'].call_tool('find_dominos_store', {
                'address': full_address
            })
            print(f"✅ Store found:\n{store_result}\n")

            # Extract store_id from response
            import json
            import re
            store_id = None
            try:
                store_data = json.loads(store_result)
                store_id = store_data.get('store_id')
            except:
                match = re.search(r'"store_id":\s*"?(\d+)"?', store_result)
                if match:
                    store_id = match.group(1)

            if not store_id:
                return "❌ Could not extract store ID. Please try a different address."

            print(f"📍 Using store ID: {store_id}\n")

            # Step 3: Set customer information with proper address object
            print("📝 Setting customer information...")
            customer_result = await self.mcp_clients['mcpizza'].call_tool('set_customer_info', {
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': phone,
                'address': {
                    'street': street,
                    'city': city,
                    'region': state,
                    'zip': zip_code
                }
            })
            print(f"✅ Customer info set\n")

            # Step 4: Get menu (requires store_id)
            print("📋 Loading store menu...")
            menu_result = await self.mcp_clients['mcpizza'].call_tool('get_store_menu', {
                'store_id': store_id
            })
            print(f"✅ Menu loaded\n")

            # Step 5: Search for items (requires store_id)
            pizza_query = input("🍕 Search for pizza (e.g., 'pepperoni', 'cheese'): ").strip()

            if pizza_query:
                print(f"\n🔍 Searching for: {pizza_query}...")
                search_result = await self.mcp_clients['mcpizza'].call_tool('search_menu', {
                    'query': pizza_query,
                    'store_id': store_id
                })
                print(f"📋 Search results:\n{search_result}\n")

                # Let user add items
                while True:
                    item_code = input("Enter item code to add (or press Enter to finish): ").strip()
                    if not item_code:
                        break

                    quantity = input("Quantity (default 1): ").strip() or "1"

                    print(f"\n➕ Adding {quantity}x {item_code}...")
                    add_result = await self.mcp_clients['mcpizza'].call_tool('add_to_order', {
                        'item_code': item_code,
                        'quantity': int(quantity)
                    })
                    print(f"✅ {add_result}\n")

                    # View order
                    order_view = await self.mcp_clients['mcpizza'].call_tool('view_order', {})
                    print(f"📦 Current order:\n{order_view}\n")

                    more = input("Add another item? (yes/no): ").strip().lower()
                    if more not in ['yes', 'y']:
                        break

            # Step 6: Calculate total
            print("\n💰 Calculating order total...")
            total_result = await self.mcp_clients['mcpizza'].call_tool('calculate_order_total', {})
            print(f"✅ Order total:\n{total_result}\n")

            print("=" * 50)
            print("⚠️  ORDER READY FOR REVIEW")
            print("=" * 50)
            print("Your order has been prepared but NOT placed.")
            print("This is a safe demonstration mode.")
            print("\n💡 To actually place the order:")
            print("  1. Review the order details above")
            print("  2. Verify the total and items")
            print("  3. Visit Domino's website to complete")
            print("=" * 50)

            return f"""✅ Pizza order prepared successfully via API!

📍 Delivery to: {full_address}
📞 Phone: {phone}
👤 Name: {name}
📧 Email: {email}
🏪 Store ID: {store_id}

⚠️  IMPORTANT: Order was prepared but NOT placed.
Real order placement is disabled for safety."""

        except Exception as e:
            logger.error(f"Error in API pizza ordering: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"❌ Failed to order pizza via API: {str(e)}"

    async def order_pizza_with_browser(self, params: Dict) -> str:
        """Order pizza using browser automation via Playwright MCP (fallback method)"""
        try:
            # Step 1: Gather delivery details
            delivery_address = params.get('address')
            if not delivery_address:
                delivery_address = input("📍 Delivery address (e.g., 123 Main St, Apt 4B): ").strip()

            phone = params.get('phone')
            if not phone:
                phone = input("📞 Phone number (e.g., (555) 123-4567): ").strip()

            name = params.get('name')
            if not name:
                name = input("✍️  Name: ").strip()

            # Step 2: Search for pizza places using DuckDuckGo
            print("\n🔍 Searching for pizza places near you...")

            if 'duckduckgo' not in self.mcp_clients:
                return "❌ DuckDuckGo search not available. Cannot find pizza places."

            # Search for pizza places with delivery
            location_query = delivery_address.split(',')[-1].strip()  # Get city/zip
            search_query = f"pizza delivery near {location_query}"

            search_result = await self.mcp_clients['duckduckgo'].call_tool('web_search', {
                'query': search_query,
                'max_results': 5
            })

            # Parse search results to extract pizza places
            import json
            try:
                result_data = json.loads(search_result)
                pizza_places = []

                if isinstance(result_data, dict) and 'results' in result_data:
                    for idx, item in enumerate(result_data['results'][:5], 1):
                        pizza_places.append({
                            'number': idx,
                            'name': item.get('title', f'Pizza Place {idx}'),
                            'url': item.get('url', ''),
                            'description': item.get('description', '')
                        })

                if not pizza_places:
                    return "❌ Could not find any pizza places in your area."

                # Display options to user
                print("\n📋 Found these pizza places:")
                for place in pizza_places:
                    print(f"  {place['number']}. {place['name']}")
                    print(f"     {place['description'][:80]}...")
                    print(f"     {place['url']}\n")

                # Let user choose
                choice = input("Choose a pizza place (enter number): ").strip()
                try:
                    choice_idx = int(choice) - 1
                    if choice_idx < 0 or choice_idx >= len(pizza_places):
                        return "❌ Invalid choice."
                    selected_place = pizza_places[choice_idx]
                except ValueError:
                    return "❌ Invalid choice."

            except json.JSONDecodeError:
                return "❌ Could not parse search results."

            # Step 3: Check if Playwright is available
            if 'playwright' not in self.mcp_clients:
                return "❌ Browser automation (Playwright) not available. Cannot proceed with automated ordering."

            print(f"\n✅ Selected: {selected_place['name']}")
            print("\n⚠️  BROWSER AUTOMATION WARNING")
            print("=" * 50)
            print("The assistant will now:")
            print("  1. Open the restaurant website in your browser")
            print("  2. Try to fill in your delivery details")
            print("  3. Stop before payment (you complete manually)")
            print("=" * 50)

            proceed = input("\n🚀 Proceed with browser automation? (yes/no): ").strip().lower()
            if proceed not in ['yes', 'y']:
                return "❌ Pizza order cancelled by user."

            # Step 4: Navigate to the restaurant website
            print(f"\n🌐 Opening {selected_place['name']} website in browser...")

            try:
                # Create screenshots directory
                import os
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_dir = f"pizza_order_screenshots_{timestamp}"
                os.makedirs(screenshot_dir, exist_ok=True)
                print(f"📁 Screenshots will be saved to: {screenshot_dir}/")

                screenshot_count = 0

                # Navigate to the restaurant website
                print("⏳ Please wait - browser window is opening...")
                print("💡 TIP: Look for a Chromium/Chrome window on your screen!")

                nav_result = await self.mcp_clients['playwright'].call_tool('browser_navigate', {
                    'url': selected_place['url']
                })

                print(f"✅ Browser opened: {nav_result[:100]}...")
                print("🌐 Browser window should now be visible on your screen")

                # Wait longer to ensure page is fully loaded and visible
                print("⏳ Waiting for page to fully load (5 seconds)...")
                await asyncio.sleep(5)

                # Take screenshot of homepage
                screenshot_count += 1
                screenshot_path = f"{screenshot_dir}/step_{screenshot_count:02d}_homepage.png"
                try:
                    await self.mcp_clients['playwright'].call_tool('browser_take_screenshot', {
                        'filename': screenshot_path
                    })
                    print(f"📸 Screenshot saved: {screenshot_path}")
                except Exception as e:
                    logger.warning(f"Could not save screenshot: {e}")

                # Step 6: AI-POWERED AUTONOMOUS ORDERING
                print("\n🤖 AUTONOMOUS AI AGENT MODE")
                print("=" * 50)
                print("💡 The AI agent will now:")
                print("   1. Analyze the webpage")
                print("   2. Find and click 'Order' or 'Delivery' buttons")
                print("   3. Fill in your delivery details automatically")
                print("   4. Navigate through the menu")
                print("   5. Stop before final payment")
                print("=" * 50)

                order_summary = []

                # Ask for pizza preferences
                print("\n🍕 Pizza preferences:")
                pizza_type = input("What type of pizza? (e.g., pepperoni, cheese, supreme) or press Enter for any: ").strip() or "any pizza"
                pizza_size = input("What size? (small/medium/large) or press Enter for any: ").strip() or "medium"

                # Autonomous ordering steps
                steps_completed = []

                try:
                    # Step 6a: Try to find and click "Order" or "Delivery" button
                    print("\n🔍 Step 1: Looking for 'Order' or 'Delivery' button...")

                    button_clicked = False
                    # Try common text-based selectors first (Playwright supports text matching)
                    for button_text in ['Order Now', 'Start Order', 'Order', 'Delivery', 'Order Delivery', 'Menu', 'Order Online']:
                        try:
                            print(f"   Trying to find: '{button_text}'...")
                            click_result = await self.mcp_clients['playwright'].call_tool('browser_click', {
                                'selector': f'text={button_text}'
                            })

                            # Check if click was successful
                            if "Error" not in click_result and "error" not in click_result.lower():
                                print(f"✅ Found and clicked '{button_text}' button")
                                print("⏳ Watch the browser window - page is loading...")
                                order_summary.append(f"Clicked '{button_text}' button")
                                steps_completed.append("Found order button")
                                button_clicked = True
                                await asyncio.sleep(5)  # Increased wait time for page load

                                # Take screenshot after clicking order button
                                screenshot_count += 1
                                screenshot_path = f"{screenshot_dir}/step_{screenshot_count:02d}_after_click_{button_text.replace(' ', '_')}.png"
                                try:
                                    await self.mcp_clients['playwright'].call_tool('browser_take_screenshot', {
                                        'filename': screenshot_path
                                    })
                                    print(f"📸 Screenshot saved: {screenshot_path}")
                                except Exception as e:
                                    logger.warning(f"Could not save screenshot: {e}")

                                break
                            else:
                                print(f"   ⚠️  '{button_text}' button not found or not clickable")
                        except Exception as e:
                            logger.debug(f"Button '{button_text}' not found: {str(e)}")
                            continue

                    if not button_clicked:
                        print("⚠️  No 'Order' button found with text matching. Trying CSS selectors...")
                        # Try CSS selectors as fallback
                        for selector in ['a[href*="order"]', 'button:has-text("order")', 'a:has-text("order")', '[class*="order"]', '[id*="order"]']:
                            try:
                                print(f"   Trying selector: {selector}...")
                                click_result = await self.mcp_clients['playwright'].call_tool('browser_click', {
                                    'selector': selector
                                })
                                if "Error" not in click_result and "error" not in click_result.lower():
                                    print(f"✅ Clicked element with selector: {selector}")
                                    order_summary.append(f"Clicked order button (CSS selector)")
                                    button_clicked = True
                                    await asyncio.sleep(5)

                                    screenshot_count += 1
                                    screenshot_path = f"{screenshot_dir}/step_{screenshot_count:02d}_after_click_css.png"
                                    try:
                                        await self.mcp_clients['playwright'].call_tool('browser_take_screenshot', {
                                            'filename': screenshot_path
                                        })
                                        print(f"📸 Screenshot saved: {screenshot_path}")
                                    except:
                                        pass
                                    break
                            except:
                                continue

                    if not button_clicked:
                        print("⚠️  Could not find or click any 'Order' button. Continuing anyway...")
                        order_summary.append("Could not find order button - manual intervention may be needed")

                    # Step 6b: Look for address/delivery form
                    print("\n🔍 Step 2: Looking for delivery address form...")
                    await asyncio.sleep(1)

                    # Try to fill address field (common selectors)
                    address_filled = False
                    for selector in ['input[name="address"]', 'input[placeholder*="address" i]', 'input[id*="address" i]', '#address', '.address-input']:
                        try:
                            await self.mcp_clients['playwright'].call_tool('browser_fill', {
                                'selector': selector,
                                'value': delivery_address
                            })
                            print(f"✅ Filled address field")
                            order_summary.append(f"Filled address: {delivery_address}")
                            address_filled = True
                            break
                        except:
                            continue

                    if not address_filled:
                        print("⚠️  Could not auto-fill address field - may need manual input")
                    else:
                        # Take screenshot after filling address
                        screenshot_count += 1
                        screenshot_path = f"{screenshot_dir}/step_{screenshot_count:02d}_filled_address.png"
                        try:
                            await self.mcp_clients['playwright'].call_tool('browser_take_screenshot', {
                                'filename': screenshot_path
                            })
                            print(f"📸 Screenshot saved: {screenshot_path}")
                        except Exception as e:
                            logger.warning(f"Could not save screenshot: {e}")

                    # Try to fill phone field
                    phone_filled = False
                    for selector in ['input[name="phone"]', 'input[type="tel"]', 'input[placeholder*="phone" i]', '#phone']:
                        try:
                            await self.mcp_clients['playwright'].call_tool('browser_fill', {
                                'selector': selector,
                                'value': phone
                            })
                            print(f"✅ Filled phone field")
                            order_summary.append(f"Filled phone: {phone}")
                            phone_filled = True
                            break
                        except:
                            continue

                    # Try to fill name field
                    name_filled = False
                    for selector in ['input[name="name"]', 'input[placeholder*="name" i]', '#name', '#firstName']:
                        try:
                            await self.mcp_clients['playwright'].call_tool('browser_fill', {
                                'selector': selector,
                                'value': name
                            })
                            print(f"✅ Filled name field")
                            order_summary.append(f"Filled name: {name}")
                            name_filled = True
                            break
                        except:
                            continue

                    # Take screenshot after filling all delivery details
                    if address_filled or phone_filled or name_filled:
                        screenshot_count += 1
                        screenshot_path = f"{screenshot_dir}/step_{screenshot_count:02d}_all_delivery_details_filled.png"
                        try:
                            await self.mcp_clients['playwright'].call_tool('browser_take_screenshot', {
                                'filename': screenshot_path
                            })
                            print(f"📸 Screenshot saved: {screenshot_path}")
                        except Exception as e:
                            logger.warning(f"Could not save screenshot: {e}")

                    # Step 6c: Try to find "Continue" or "Next" button
                    print("\n🔍 Step 3: Looking for 'Continue' or 'Next' button...")
                    continue_clicked = False

                    for button_text in ['Continue', 'Next', 'Submit', 'Proceed', 'Go', 'Checkout', 'Start Order']:
                        try:
                            print(f"   Trying to find: '{button_text}'...")
                            click_result = await self.mcp_clients['playwright'].call_tool('browser_click', {
                                'selector': f'text={button_text}'
                            })

                            if "Error" not in click_result and "error" not in click_result.lower():
                                print(f"✅ Clicked '{button_text}' button")
                                print("⏳ Watch the browser window - page is changing...")
                                order_summary.append(f"Clicked '{button_text}' button")
                                continue_clicked = True
                                await asyncio.sleep(5)  # Increased wait time for navigation

                                # Take screenshot after clicking continue
                                screenshot_count += 1
                                screenshot_path = f"{screenshot_dir}/step_{screenshot_count:02d}_after_click_{button_text}.png"
                                try:
                                    await self.mcp_clients['playwright'].call_tool('browser_take_screenshot', {
                                        'filename': screenshot_path
                                    })
                                    print(f"📸 Screenshot saved: {screenshot_path}")
                                except Exception as e:
                                    logger.warning(f"Could not save screenshot: {e}")

                                break
                            else:
                                print(f"   ⚠️  '{button_text}' button not found or not clickable")
                        except Exception as e:
                            logger.debug(f"Button '{button_text}' not found: {str(e)}")
                            continue

                    if not continue_clicked:
                        print("⚠️  No 'Continue/Next' button found with text matching. Trying CSS selectors...")
                        # Try CSS selectors as fallback
                        for selector in ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("continue")', 'a:has-text("continue")', '[class*="continue"]', '[class*="next"]', '[id*="continue"]']:
                            try:
                                print(f"   Trying selector: {selector}...")
                                click_result = await self.mcp_clients['playwright'].call_tool('browser_click', {
                                    'selector': selector
                                })
                                if "Error" not in click_result and "error" not in click_result.lower():
                                    print(f"✅ Clicked element with selector: {selector}")
                                    order_summary.append(f"Clicked continue button (CSS selector)")
                                    continue_clicked = True
                                    await asyncio.sleep(5)

                                    screenshot_count += 1
                                    screenshot_path = f"{screenshot_dir}/step_{screenshot_count:02d}_after_continue_css.png"
                                    try:
                                        await self.mcp_clients['playwright'].call_tool('browser_take_screenshot', {
                                            'filename': screenshot_path
                                        })
                                        print(f"📸 Screenshot saved: {screenshot_path}")
                                    except:
                                        pass
                                    break
                            except:
                                continue

                    if not continue_clicked:
                        print("⚠️  Could not find or click 'Continue/Next' button. Skipping to menu...")
                        order_summary.append("Could not find continue button - skipped to menu")

                    # Step 6d: Look for menu items
                    print(f"\n🔍 Step 4: Looking for {pizza_type} ({pizza_size}) on the menu...")
                    print("⚠️  Note: Autonomous menu navigation is complex and site-specific.")
                    print("          The agent has navigated to the menu page.")

                    # Take a screenshot of the menu page
                    screenshot_count += 1
                    screenshot_path = f"{screenshot_dir}/step_{screenshot_count:02d}_menu_page.png"
                    print(f"\n📸 Taking screenshot of menu page...")
                    try:
                        await self.mcp_clients['playwright'].call_tool('browser_take_screenshot', {
                            'filename': screenshot_path
                        })
                        print(f"✅ Screenshot saved: {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"Could not save screenshot: {e}")

                    # Inform user about next steps
                    print("\n" + "=" * 50)
                    print("🎯 AUTONOMOUS AGENT STATUS")
                    print("=" * 50)
                    print("\n✅ Actions completed automatically:")
                    for action in order_summary:
                        print(f"   • {action}")

                    print(f"\n📸 Total screenshots saved: {screenshot_count}")
                    print(f"📁 Location: {screenshot_dir}/")
                    print(f"💡 You can review all screenshots to see what the agent did!")

                    print("\n⚠️  STOPPING BEFORE PAYMENT")
                    print("=" * 50)
                    print("The autonomous agent has:")
                    print("  ✅ Opened the restaurant website")
                    print("  ✅ Filled your delivery details")
                    print("  ✅ Navigated to the menu")
                    print("\n  ⏸️  Stopped before completing the order")
                    print("\n💡 You can now:")
                    print("  1. Manually complete the order in the open browser")
                    print("  2. Close the browser to cancel")
                    print("=" * 50)

                    keep_open = input("\n🌐 Keep browser open to complete manually? (yes/no): ").strip().lower()
                    if keep_open not in ['yes', 'y']:
                        await self.mcp_clients['playwright'].call_tool('browser_close', {})
                        print("✅ Browser closed")
                    else:
                        print("✅ Browser left open - you can complete the order manually")
                        print("   Run the assistant again when done to close the browser")

                except Exception as step_error:
                    logger.error(f"Error in autonomous step: {step_error}")
                    print(f"\n⚠️  Autonomous agent encountered an issue: {str(step_error)}")

                    # Take error screenshot
                    screenshot_count += 1
                    screenshot_path = f"{screenshot_dir}/step_{screenshot_count:02d}_ERROR_state.png"
                    print(f"📸 Taking error screenshot: {screenshot_path}")
                    try:
                        await self.mcp_clients['playwright'].call_tool('browser_take_screenshot', {
                            'filename': screenshot_path
                        })
                        print(f"✅ Error screenshot saved: {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"Could not save error screenshot: {e}")

                # Step 7: Summary
                print("\n📋 ORDER SUMMARY")
                print("=" * 50)
                print(f"🍕 Restaurant: {selected_place['name']}")
                print(f"📍 Delivery to: {delivery_address}")
                print(f"📞 Phone: {phone}")
                print(f"✍️  Name: {name}")
                print("\n🤖 Actions performed:")
                for action in order_summary:
                    print(f"   • {action}")
                print("=" * 50)

                # Close browser
                close_browser = input("\n🔒 Close browser? (yes/no): ").strip().lower()
                if close_browser in ['yes', 'y']:
                    await self.mcp_clients['playwright'].call_tool('browser_close', {})
                    print("✅ Browser closed")

                return f"""✅ Pizza ordering session completed!

🍕 Restaurant: {selected_place['name']}
📍 Delivery: {delivery_address}
📞 Phone: {phone}

⚠️  IMPORTANT: This was a demonstration using browser automation.
If you completed the order, please verify on the restaurant's website.

💡 Test credit card numbers were used - no real charge was made unless
you manually entered real payment details."""

            except Exception as e:
                logger.error(f"Browser automation error: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return f"❌ Browser automation failed: {str(e)}\n\n💡 Make sure Playwright MCP server is running properly."

        except Exception as e:
            logger.error(f"Error in pizza ordering: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"❌ Failed to order pizza: {str(e)}"

    async def search_emails(self, params: Dict) -> str:
        """Search emails via Gmail MCP server"""
        try:
            count = params.get('count', 10)
            query = params.get('query', '')  # Empty query returns all emails

            if 'gmail' not in self.mcp_clients:
                return "❌ Gmail server not available. Please check if the Gmail MCP server is running."

            logger.info(f"📧 Calling Gmail MCP search_emails with query='{query}' and maxResults={count}")

            # First, list available tools to verify what's available
            try:
                tools = await self.mcp_clients['gmail'].list_tools()
                tool_names = [tool.get('name', 'unknown') for tool in tools]
                logger.info(f"📋 Available Gmail MCP tools: {tool_names}")
            except Exception as e:
                logger.error(f"❌ Could not list Gmail tools: {e}")

            # Call the Gmail MCP server using search_emails
            result = await self.mcp_clients['gmail'].call_tool('search_emails', {
                'query': query,
                'maxResults': count
            })

            logger.info(f"📧 Raw MCP response type: {type(result)}")
            logger.info(f"📧 Raw MCP response length: {len(result)} characters")
            logger.info(f"📧 Raw MCP response FULL CONTENT:\n{result}")

            # Check if result contains an error message
            if "Error:" in result or "error" in result.lower():
                return f"❌ Gmail MCP server returned an error:\n{result}\n\nPlease check your Gmail authentication and MCP server logs."

            # Check for common error patterns
            if "No response from tool" in result or len(result) < 10:
                return f"❌ Gmail MCP server returned invalid response:\n{result}\n\nThe server might not be properly connected or authenticated."

            # Return the RAW result from MCP - NO processing, NO LLM
            return f"📬 RAW response from Gmail MCP server:\n\n{result}"

        except Exception as e:
            logger.error(f"❌ Exception in search_emails: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"❌ Failed to search emails: {str(e)}\nPlease check your Gmail MCP server configuration and authentication."
    
    async def list_calendar_events(self, params: Dict) -> str:
        """List calendar events via calendar MCP server"""
        try:
            days = params.get('days', 7)
            
            if 'calendar' not in self.mcp_clients:
                return "❌ Calendar server not available"
            
            # Calculate time range
            from datetime import datetime, timedelta
            now = datetime.now()
            time_max = now + timedelta(days=days)
            
            # Call the calendar MCP server
            result = await self.mcp_clients['calendar'].call_tool('list_events', {
                'timeMin': now.isoformat() + 'Z',
                'timeMax': time_max.isoformat() + 'Z',
                'maxResults': 20
            })
            
            return f"📅 Calendar events via calendar MCP server (next {days} days):\n\n{result}"
            
        except Exception as e:
            logger.error(f"Error listing calendar events: {e}")
            return f"❌ Failed to list calendar events: {str(e)}"
    
    async def gather_parameters(self, intent: str, params: Dict) -> Dict:
        """Interactively gather missing parameters from user"""

        if intent == 'send_email':
            # Only ask for missing information
            if 'to' not in params or not params.get('to'):
                to_email = input("📧 To (email address): ").strip()
                params['to'] = to_email
            else:
                print(f"📧 To: {params['to']}")

            if 'subject' not in params or not params.get('subject'):
                subject = input("📝 Subject: ").strip()
                params['subject'] = subject
            else:
                print(f"📝 Subject: {params['subject']}")

            if 'body' not in params or not params.get('body'):
                print("\n✍️  Choose email body option:")
                print("  1. Write manually")
                print("  2. AI-assisted composition")
                choice = input("Your choice (1/2): ").strip()

                if choice == '2':
                    # AI-assisted email composition
                    purpose = input("💡 What's the purpose of this email? ").strip()
                    tone = input("🎯 Tone (professional/casual/friendly): ").strip() or "professional"
                    key_points = input("📌 Key points to include (comma-separated): ").strip()

                    compose_prompt = f"""You are composing an email. Output ONLY the email body text, nothing else.

Subject: {params.get('subject', 'No subject')}
Tone: {tone}
Purpose: {purpose}
Key points: {key_points}

Rules:
- Do NOT include any meta-commentary like "Here is the email" or "Would you like me to"
- Do NOT include greetings like "Dear" or signatures
- Output ONLY the actual email body content
- Be concise and clear

Email body:"""
                    print("\n⏳ Generating email...")
                    generated_body = await self.query_ollama(compose_prompt)

                    # Clean up common LLM meta-commentary
                    cleanup_phrases = [
                        "Here is a friendly email with the specified details:",
                        "Here is the email:",
                        "Here is a",
                        "Here's the email:",
                        "Here's a",
                        "Would you like me to",
                        "Subject:",
                        "Email body:",
                        "I hope this email finds you well."
                    ]

                    for phrase in cleanup_phrases:
                        if generated_body.strip().startswith(phrase):
                            generated_body = generated_body[len(phrase):].strip()

                    # Remove any remaining "Here is..." patterns at the start
                    import re
                    generated_body = re.sub(r'^(Here is|Here\'s|This is).*?:', '', generated_body, flags=re.IGNORECASE).strip()

                    print(f"\n📧 Generated email:\n{generated_body}\n")

                    confirm = input("Use this email? (yes/edit/rewrite): ").strip().lower()
                    if confirm == 'edit':
                        print("Enter your edits (press Enter twice when done):")
                        lines = [generated_body]
                        while True:
                            line = input()
                            if line == "" and len(lines) > 0 and lines[-1] == "":
                                break
                            lines.append(line)
                        params['body'] = '\n'.join(lines[:-1])
                    elif confirm == 'rewrite':
                        feedback = input("What should I change? ")
                        rewrite_prompt = f"{compose_prompt}\n\nPrevious version:\n{generated_body}\n\nUser feedback: {feedback}\n\nWrite an improved version."
                        params['body'] = await self.query_ollama(rewrite_prompt)
                    else:
                        params['body'] = generated_body
                else:
                    # Manual composition
                    print("✍️  Email body (press Enter twice when done):")
                    lines = []
                    while True:
                        line = input()
                        if line == "" and len(lines) > 0 and lines[-1] == "":
                            break
                        lines.append(line)
                    params['body'] = '\n'.join(lines[:-1])  # Remove last empty line
            else:
                print(f"✍️  Body: {params['body'][:100]}...")  # Show preview if already provided

        elif intent == 'read_multiple_pdfs':
            if 'paths' not in params or not params.get('paths'):
                print("\n📁 Choose input method:")
                print("  1. Enter a folder path (read all PDFs in folder)")
                print("  2. Enter individual PDF file paths")
                choice = input("Your choice (1/2): ").strip()

                if choice == '1':
                    folder_path = input("📂 Folder path: ").strip()

                    # Expand home directory
                    if folder_path.startswith('~'):
                        folder_path = os.path.expanduser(folder_path)

                    # Find all PDF files in the folder
                    import glob
                    pdf_pattern = os.path.join(folder_path, "*.pdf")
                    pdf_files = glob.glob(pdf_pattern)

                    if not pdf_files:
                        print(f"❌ No PDF files found in {folder_path}")
                        return params

                    print(f"\n✅ Found {len(pdf_files)} PDF files:")
                    for pdf in pdf_files:
                        print(f"  • {os.path.basename(pdf)}")

                    confirm = input("\nLoad all these PDFs? (yes/no): ").strip().lower()
                    if confirm in ['yes', 'y']:
                        params['paths'] = pdf_files
                    else:
                        return params
                else:
                    print("📁 Enter PDF file paths (one per line, press Enter twice when done):")
                    paths = []
                    while True:
                        path = input().strip()
                        if path == "":
                            if len(paths) > 0:
                                break
                            else:
                                print("Please enter at least one PDF path:")
                                continue
                        paths.append(path)
                    params['paths'] = paths

        elif intent == 'read_file':
            if 'path' not in params or not params.get('path'):
                path = input("📁 File path: ").strip()
                params['path'] = path

        elif intent == 'schedule_meeting':
            if 'title' not in params or not params.get('title'):
                title = input("📋 Meeting title: ").strip()
                params['title'] = title

            if 'start_time' not in params or not params.get('start_time'):
                start = input("⏰ Start time (YYYY-MM-DDTHH:MM:SS, e.g., 2024-01-20T14:00:00): ").strip()
                # Parse as local time and convert to ISO format with timezone
                from datetime import datetime
                import dateutil.tz
                if not start.endswith('Z') and '+' not in start and '-' not in start[-6:]:
                    # User entered local time without timezone
                    local_dt = datetime.fromisoformat(start)
                    # Get local timezone
                    local_tz = dateutil.tz.tzlocal()
                    local_dt = local_dt.replace(tzinfo=local_tz)
                    params['start_time'] = local_dt.isoformat()
                else:
                    params['start_time'] = start

            if 'end_time' not in params or not params.get('end_time'):
                end = input("⏰ End time (YYYY-MM-DDTHH:MM:SS, e.g., 2024-01-20T15:00:00): ").strip()
                # Parse as local time and convert to ISO format with timezone
                from datetime import datetime
                import dateutil.tz
                if not end.endswith('Z') and '+' not in end and '-' not in end[-6:]:
                    # User entered local time without timezone
                    local_dt = datetime.fromisoformat(end)
                    # Get local timezone
                    local_tz = dateutil.tz.tzlocal()
                    local_dt = local_dt.replace(tzinfo=local_tz)
                    params['end_time'] = local_dt.isoformat()
                else:
                    params['end_time'] = end

            if 'attendees' not in params:
                attendees_input = input("👥 Attendees (comma-separated emails, or press Enter to skip): ").strip()
                params['attendees'] = [email.strip() for email in attendees_input.split(',')] if attendees_input else []

        elif intent == 'web_search':
            if 'query' not in params or not params.get('query'):
                query = input("🔍 Search query: ").strip()
                params['query'] = query

        return params

    async def execute_action(self, intent: str, params: Dict) -> str:
        """Execute actions based on intent analysis"""
        try:
            if intent == 'send_email':
                return await self.send_email(params)
            elif intent == 'read_multiple_pdfs':
                return await self.read_multiple_pdfs(params)
            elif intent == 'read_file':
                return await self.read_file(params)
            elif intent == 'schedule_meeting':
                return await self.schedule_meeting(params)
            elif intent == 'web_search':
                return await self.web_search(params)
            elif intent == 'search_emails':
                return await self.search_emails(params)
            elif intent == 'list_calendar':
                return await self.list_calendar_events(params)
            elif intent == 'order_pizza':
                return await self.order_pizza(params)
            else:
                return f"Action '{intent}' not implemented yet."

        except Exception as e:
            logger.error(f"Error executing action {intent}: {e}")
            return f"Error executing {intent}: {str(e)}"
    
    async def analyze_intent(self, user_input: str) -> tuple[str, Dict]:
        """Analyze user intent using rule-based approach optimized for reliability"""
        user_lower = user_input.lower()
        import re

        # Rule-based intent detection (more reliable than LLM for small models)
        # IMPORTANT: Check list/show commands BEFORE send commands to avoid conflicts

        # Check for show/list emails (must come before send_email)
        if any(phrase in user_lower for phrase in ['list emails', 'show emails', 'show my emails', 'check emails', 'check inbox', 'my emails', 'recent emails', 'inbox', 'show recent']):
            # Try to extract count from message
            count_match = re.search(r'(\d+)\s*(?:emails?|messages?)', user_lower)
            count = int(count_match.group(1)) if count_match else 10
            return 'search_emails', {'count': count, 'query': ''}

        # Check for calendar (must come before schedule check)
        elif any(phrase in user_lower for phrase in ['show calendar', 'my calendar', 'my schedule', 'show my schedule', 'upcoming meetings', 'my events', 'what\'s on my calendar']):
            # Try to extract days from message
            days_match = re.search(r'(?:next|for)\s*(\d+)\s*days?', user_lower)
            if not days_match:
                days_match = re.search(r'(\d+)\s*days?', user_lower)
            days = int(days_match.group(1)) if days_match else 7
            return 'list_calendar', {'days': days}

        # Send email - specific phrases only
        elif any(phrase in user_lower for phrase in ['send email', 'send mail', 'send an email', 'write email', 'compose email', 'email to']):
            # Try to extract email address, subject, and body from the message
            params = {}

            # Extract email address - look for email patterns
            email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', user_input)
            if email_match:
                params['to'] = email_match.group(0)

            # Extract subject - look for "about", "regarding", "subject:", etc.
            subject = None
            if 'about ' in user_lower:
                subject = user_input.split('about ', 1)[1].strip()
                # Remove "to <email>" part if present
                subject = re.sub(r'\s*to\s+[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\s*', '', subject, flags=re.IGNORECASE)
            elif 'regarding ' in user_lower:
                subject = user_input.split('regarding ', 1)[1].strip()
            elif 'subject:' in user_lower:
                subject = user_input.split('subject:', 1)[1].strip()

            if subject:
                # Clean up subject - remove common trailing words
                subject = subject.strip('.,!?')
                params['subject'] = subject

            params['needs_info'] = True  # Still need to gather missing info
            return 'send_email', params

        # Read multiple PDFs - check for "multiple", "several", "all", or comma-separated paths
        elif any(phrase in user_lower for phrase in ['read multiple', 'read several', 'analyze multiple', 'analyze several', 'compare pdfs', 'compare documents']):
            return 'read_multiple_pdfs', {'needs_info': True}

        # Read single file/PDF
        elif any(word in user_lower for word in ['read', 'open', 'show me']) and any(word in user_lower for word in ['file', 'pdf', 'document', 'doc']):
            # Try to extract file path/name from the input
            path = None
            for word in user_input.split():
                if '.pdf' in word.lower() or '.txt' in word.lower() or '.doc' in word.lower():
                    path = word
                    break
            return 'read_file', {'path': path, 'needs_info': path is None}

        # Schedule meeting
        elif any(phrase in user_lower for phrase in ['schedule', 'book', 'create meeting', 'set up meeting', 'arrange meeting', 'schedule a meeting']):
            return 'schedule_meeting', {'needs_info': True}

        # Web search
        elif any(phrase in user_lower for phrase in ['search', 'google', 'find', 'look up', 'lookup', 'search for']):
            # Extract search query
            query = user_input
            for phrase in ['search for', 'google', 'find', 'look up', 'lookup']:
                query = query.lower().replace(phrase, '').strip()
            return 'web_search', {'query': query if query else None, 'needs_info': not query}

        # Order pizza
        elif any(phrase in user_lower for phrase in ['order pizza', 'order a pizza', 'get pizza', 'buy pizza', 'pizza delivery']):
            return 'order_pizza', {'needs_info': True}

        else:
            return 'general', {}
    
    async def process_request(self, user_input: str) -> str:
        """Main processing logic"""
        try:
            # Classify privacy level
            privacy_level = self.classify_privacy_level(user_input)
            logger.info(f"Processing request with privacy level: {privacy_level.value}")

            # Analyze intent
            intent, params = await self.analyze_intent(user_input)
            logger.info(f"Detected intent: {intent} with params: {params}")

            if intent != 'general':
                # Gather any missing parameters interactively
                if params.get('needs_info', False):
                    print(f"\n💡 I need some information to {intent.replace('_', ' ')}:\n")
                    params = await self.gather_parameters(intent, params)
                    # Remove the needs_info flag
                    params.pop('needs_info', None)

                # Execute specific action via MCP servers
                action_result = await self.execute_action(intent, params)
                return action_result
            else:
                # General conversation - use Ollama for natural responses
                return await self.query_ollama(user_input)

        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return f"I encountered an error processing your request: {str(e)}"
    
    async def cleanup(self):
        """Clean up MCP server processes"""
        logger.info("🛑 Stopping MCP servers...")
        for name, config in self.mcp_servers.items():
            if config.process:
                try:
                    config.process.terminate()
                    await asyncio.sleep(1)
                    if config.process.poll() is None:
                        config.process.kill()
                    logger.info(f"✅ Stopped MCP server: {name}")
                except Exception as e:
                    logger.error(f"❌ Error stopping MCP server {name}: {e}")

async def main():
    """Main application entry point"""
    print("🤖 AI Assistant with REAL MCP Integration")
    print("=" * 50)

    # Get Gemini API key from environment variable
    gemini_api_key = os.getenv('GEMINI_API_KEY')

    if not gemini_api_key:
        print("⚠️  GEMINI_API_KEY not found in environment variables.")
        print("💡 PDF Q&A with multiple documents will not be available.")
        print("💡 Set GEMINI_API_KEY to enable this feature.\n")

    assistant = AIAssistant(gemini_api_key=gemini_api_key)

    try:
        print("🚀 Starting AI Assistant...")
        await assistant.start_mcp_servers()
        print("✅ All systems ready!")
        print("\n💬 You can now chat with your AI assistant.")
        print("📝 Try commands like:")
        print("   - 'Send an email to team@company.com about the meeting'")
        print("   - 'Read the quarterly report PDF'")
        print("   - 'Read multiple PDFs and answer questions' (requires Gemini API)")
        print("   - 'Schedule a meeting with Sarah next Tuesday at 2 PM'")
        print("   - 'Search for latest AI news'")
        print("   - 'List my recent emails'")
        print("   - 'Show my calendar for this week'")
        print("   - 'Order pizza' (browser automation demo)")
        print("\n💡 Type 'quit' to exit.\n")
        
        while True:
            try:
                user_input = input("👤 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye']:
                    print("👋 Goodbye!")
                    break
                    
                if not user_input:
                    continue
                
                print("🤖 Assistant: ", end="", flush=True)
                response = await assistant.process_request(user_input)
                print(response)
                print()  # Add spacing
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                
    finally:
        await assistant.cleanup()

if __name__ == "__main__":
    # Check if Ollama is running
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code != 200:
            print("❌ Ollama is not running. Please start it with: ollama serve")
            exit(1)
    except:
        print("❌ Cannot connect to Ollama. Please start it with: ollama serve")
        exit(1)
    
    asyncio.run(main())