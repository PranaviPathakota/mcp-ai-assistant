# MCPizza - Domino's Pizza Ordering MCP Server

An MCP (Model Context Protocol) server that enables AI assistants to order pizza using the unofficial Domino's API.

## Features

- **Store Locator**: Find nearest Domino's stores by address or zip code
- **Menu Search**: Search for pizzas, wings, sides, and more
- **Order Management**: Add items to cart, view order, and calculate totals
- **Customer Info**: Handle delivery addresses and contact information
- **Order Placement**: Place real orders (disabled by default for safety)

## Installation

```bash
# Create and activate virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running the Server

```bash
python -m mcpizza.server
```

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `find_dominos_store` | Find nearest Domino's location by address/zip |
| `get_store_menu` | Get full store menu |
| `search_menu` | Search for specific menu items |
| `add_to_order` | Add items to your pizza order |
| `view_order` | View current order contents and subtotal |
| `set_customer_info` | Set delivery address and contact info |
| `calculate_order_total` | Get estimated total with tax and delivery fee |
| `apply_coupon` | Apply a Domino's coupon code |
| `place_order` | Place the order (card or cash payment) |

## Usage Example

```python
# 1. Find a store
result = server.call_tool("find_dominos_store", {"address": "77840"})

# 2. Search the menu
result = server.call_tool("search_menu", {
    "query": "pepperoni pizza",
    "store_id": "1234"
})

# 3. Add items to cart
result = server.call_tool("add_to_order", {
    "item_code": "S_PIZZA",
    "quantity": 1
})

# 4. Set delivery info
result = server.call_tool("set_customer_info", {
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane@example.com",
    "phone": "555-123-4567",
    "address": {
        "street": "123 Main St",
        "city": "College Station",
        "region": "TX",
        "zip": "77840"
    }
})

# 5. Check total
result = server.call_tool("calculate_order_total", {})
```

## Safety Notes

- Uses the unofficial Domino's API (`pizzapi`) for educational purposes
- Test your order flow before enabling live placement
- Use responsibly and in accordance with Domino's terms of service

## Requirements

- Python 3.9+
- `pizzapi`, `requests`, `pydantic`, `mcp` (see requirements.txt)
- Internet connection
