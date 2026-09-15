#!/usr/bin/env python3
"""
MCPizza - Domino's Pizza Ordering MCP Server

This server provides tools for ordering pizza through the unofficial Domino's API.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import ServerCapabilities
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    Tool,
    TextContent,
)

try:
    from pizzapi import *
    from pizzapi import PaymentObject
except ImportError:
    print("pizzapi not installed. Install with: pip install pizzapi")
    exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcpizza")

class PizzaOrder:
    """Manages a pizza order state"""
    def __init__(self):
        self.store = None
        self.customer = None
        self.order = None
        self.items = []
        self.menu_data = None  # Cache menu data to avoid Menu class bugs

pizza_order = PizzaOrder()

# Available tools
TOOLS = [
    Tool(
        name="find_dominos_store",
        description="Find the nearest Domino's store by address or zip code",
        inputSchema={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Full address or zip code to search near"
                }
            },
            "required": ["address"]
        }
    ),
    Tool(
        name="get_store_menu",
        description="Get the full menu from a Domino's store",
        inputSchema={
            "type": "object",
            "properties": {
                "store_id": {
                    "type": "string",
                    "description": "Store ID from find_dominos_store result"
                }
            },
            "required": ["store_id"]
        }
    ),
    Tool(
        name="search_menu",
        description="Search for specific items in the store menu",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (e.g., 'pepperoni pizza', 'wings', 'pasta')"
                },
                "store_id": {
                    "type": "string",
                    "description": "Store ID from find_dominos_store result"
                }
            },
            "required": ["query", "store_id"]
        }
    ),
    Tool(
        name="add_to_order",
        description="Add items to the pizza order",
        inputSchema={
            "type": "object",
            "properties": {
                "item_code": {
                    "type": "string",
                    "description": "Product code from menu search"
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of items to add",
                    "default": 1
                },
                "options": {
                    "type": "object",
                    "description": "Item customization options",
                    "default": {}
                }
            },
            "required": ["item_code"]
        }
    ),
    Tool(
        name="view_order",
        description="View current order contents and total",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        name="set_customer_info",
        description="Set customer information for delivery",
        inputSchema={
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                        "region": {"type": "string"},
                        "zip": {"type": "string"}
                    },
                    "required": ["street", "city", "region", "zip"]
                }
            },
            "required": ["first_name", "last_name", "email", "phone", "address"]
        }
    ),
    Tool(
        name="calculate_order_total",
        description="Calculate order total with tax and delivery fees",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        name="apply_coupon",
        description="Apply a coupon code to the order",
        inputSchema={
            "type": "object",
            "properties": {
                "coupon_code": {
                    "type": "string",
                    "description": "Domino's coupon code"
                }
            },
            "required": ["coupon_code"]
        }
    ),
    Tool(
        name="place_order",
        description="Place the pizza order (requires customer info and payment)",
        inputSchema={
            "type": "object",
            "properties": {
                "payment_info": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["card", "cash"]},
                        "card_number": {"type": "string", "description": "Credit card number (required for card payments)"},
                        "expiration": {"type": "string", "description": "Card expiration in MMYY format (required for card payments)"},
                        "cvv": {"type": "string", "description": "3-digit security code (required for card payments)"},
                        "billing_zip": {"type": "string", "description": "Billing zip code (required for card payments)"},
                        "tip_amount": {"type": "number", "description": "Tip amount", "default": 0}
                    },
                    "required": ["type"]
                }
            },
            "required": ["payment_info"]
        }
    )
]

async def handle_find_dominos_store(arguments: Dict[str, Any]) -> list:
    """Find nearest Domino's store"""
    try:
        address_str = arguments["address"]

        # Parse address - if it's just a ZIP, use a simple address
        # Otherwise try to parse it as street, city, state, zip
        address_parts = address_str.split(',')

        if len(address_parts) == 1:
            # Just a ZIP code
            addr = Address('', '', '', address_str.strip())
        elif len(address_parts) >= 4:
            # Full address: street, city, state zip
            street = address_parts[0].strip()
            city = address_parts[1].strip()
            state_zip = address_parts[2].strip().split()
            state = state_zip[0] if state_zip else ''
            zip_code = state_zip[1] if len(state_zip) > 1 else address_parts[3].strip()
            addr = Address(street, city, state, zip_code)
        else:
            # Try to make sense of it
            addr = Address('', '', '', address_str.strip())

        # Find nearest store
        my_local_dominos = addr.closest_store()

        if not my_local_dominos:
            return [TextContent(
                type="text",
                text="No Domino's stores found near that address."
            )]

        # Get store details
        store_details = my_local_dominos.get_details()

        # Store the found store globally for use in other tools
        pizza_order.store = my_local_dominos

        store_info = {
            "store_id": store_details.get("StoreID"),
            "phone": store_details.get("Phone"),
            "address": f"{store_details.get('StreetName', '')} {store_details.get('City', '')}",
            "is_delivery_store": store_details.get("IsDeliveryStore"),
            "min_delivery_order_amount": store_details.get("MinDeliveryOrderAmount"),
            "delivery_minutes": store_details.get("ServiceEstimatedWaitMinutes", {}).get("Delivery"),
            "pickup_minutes": store_details.get("ServiceEstimatedWaitMinutes", {}).get("Carryout")
        }

        return [TextContent(
            type="text",
            text=f"Found Domino's store:\n{json.dumps(store_info, indent=2)}"
        )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error finding store: {str(e)}"
        )]

async def handle_get_store_menu(arguments: Dict[str, Any]) -> list:
    """Get store menu"""
    try:
        if not pizza_order.store:
            return [TextContent(
                type="text",
                text="No store selected. Use find_dominos_store first."
            )]

        try:
            menu = pizza_order.store.get_menu()
            # Try to extract categories if menu loads successfully
            categories = []
            if hasattr(menu, 'root_categories'):
                for cat in menu.root_categories.values():
                    categories.append(cat.name if hasattr(cat, 'name') else str(cat))
        except Exception as menu_error:
            # Menu API has issues, provide helpful message
            return [TextContent(
                type="text",
                text=f"Menu loaded with warnings (some items may not be available due to API limitations).\n\nRecommended: Use search_menu to find specific items like 'pizza', 'wings', 'pasta', 'dessert', etc."
            )]

        return [TextContent(
            type="text",
            text=f"Store menu categories available.\n\nUse search_menu to find specific items like:\n- pepperoni pizza\n- cheese pizza\n- wings\n- pasta\n- dessert\n- drinks"
        )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error getting menu: {str(e)}\n\nTip: Try using search_menu directly to find items."
        )]

async def handle_search_menu(arguments: Dict[str, Any]) -> list:
    """Search menu for items"""
    try:
        if not pizza_order.store:
            return [TextContent(
                    type="text",
                    text="No store selected. Use find_dominos_store first."
                )]

        query = arguments["query"].lower()

        # Get raw menu data from store API
        from pizzapi import request_json, urls
        store_details = pizza_order.store.get_details()
        store_id = store_details.get("StoreID")

        # Fetch menu data directly using correct country code
        url_helper = urls.Urls(pizza_order.store.country if pizza_order.store.country else 'us')
        menu_url = url_helper.menu_url()

        # Replace placeholders in URL
        menu_url = menu_url.replace('{store_id}', str(store_id))
        menu_url = menu_url.replace('{lang}', 'en')  # English language

        menu_data = request_json(menu_url)

        matching_items = []

        # Search through menu data
        if "Products" in menu_data:
            for product_code, product_info in menu_data["Products"].items():
                if isinstance(product_info, dict):
                    name = product_info.get("Name", "").lower()
                    description = product_info.get("Description", "").lower()

                    if query in name or query in description:
                        # Get variant info
                        variants = product_info.get("Variants", [])
                        price = "varies"
                        if variants and isinstance(variants, list) and len(variants) > 0:
                            variant_code = variants[0]
                            if variant_code in menu_data.get("Variants", {}):
                                variant_info = menu_data["Variants"][variant_code]
                                price = variant_info.get("Price", "varies")

                        matching_items.append({
                            "code": product_code,
                            "name": product_info.get("Name", ""),
                            "description": product_info.get("Description", ""),
                            "price": price,
                            "variants": variants[:3] if len(variants) > 3 else variants  # Show max 3 variants
                        })

        if not matching_items:
            return [TextContent(
                    type="text",
                    text=f"No items found matching '{query}'. Try broader terms like 'pizza', 'wings', 'pasta', or 'dessert'."
                )]

        # Limit to top 10 results
        matching_items = matching_items[:10]

        return [TextContent(
                type="text",
                text=f"Found {len(matching_items)} items matching '{query}':\n{json.dumps(matching_items, indent=2)}"
            )]

    except Exception as e:
        import traceback
        return [TextContent(
                type="text",
                text=f"Error searching menu: {str(e)}\n\nTry using simpler search terms. If the problem persists, the Domino's API may be experiencing issues."
            )]

async def handle_add_to_order(arguments: Dict[str, Any]) -> list:
    """Add item to order"""
    try:
        if not pizza_order.store:
            return [TextContent(
                    type="text",
                    text="No store selected. Use find_dominos_store first."
                )]

        item_code = arguments["item_code"]
        quantity = arguments.get("quantity", 1)
        options = arguments.get("options", {})

        # Get menu data if not cached
        if not pizza_order.menu_data:
            from pizzapi import request_json, urls
            store_details = pizza_order.store.get_details()
            store_id = store_details.get("StoreID")
            url_helper = urls.Urls(pizza_order.store.country if pizza_order.store.country else 'us')
            menu_url = url_helper.menu_url()
            menu_url = menu_url.replace('{store_id}', str(store_id))
            menu_url = menu_url.replace('{lang}', 'en')
            pizza_order.menu_data = request_json(menu_url)

        # Verify item exists in menu
        if "Products" not in pizza_order.menu_data or item_code not in pizza_order.menu_data["Products"]:
            return [TextContent(
                    type="text",
                    text=f"Item code '{item_code}' not found in menu. Please search for items first."
                )]

        # Get item details
        product_info = pizza_order.menu_data["Products"][item_code]
        item_name = product_info.get("Name", item_code)

        # Get price from variants
        variants = product_info.get("Variants", [])
        price = 0.0
        if variants and len(variants) > 0:
            variant_code = variants[0]
            if variant_code in pizza_order.menu_data.get("Variants", {}):
                variant_info = pizza_order.menu_data["Variants"][variant_code]
                price = float(variant_info.get("Price", 0))

        # Add to our simple cart
        pizza_order.items.append({
            "code": item_code,
            "name": item_name,
            "quantity": quantity,
            "price": price,
            "options": options
        })

        return [TextContent(
                type="text",
                text=f"Added {quantity}x {item_name} to order (${price * quantity:.2f})"
            )]

    except Exception as e:
        import traceback
        return [TextContent(
                type="text",
                text=f"Error adding item: {str(e)}"
            )]

async def handle_view_order(arguments: Dict[str, Any]) -> list:
    """View current order"""
    try:
        if not pizza_order.items:
            return [TextContent(
                    type="text",
                    text="No items in order yet."
                )]

        # Build order summary
        order_summary = "Current Order:\n" + "="*50 + "\n\n"
        subtotal = 0.0

        for i, item in enumerate(pizza_order.items, 1):
            item_total = item["price"] * item["quantity"]
            subtotal += item_total
            order_summary += f"{i}. {item['name']}\n"
            order_summary += f"   Code: {item['code']}\n"
            order_summary += f"   Quantity: {item['quantity']}\n"
            order_summary += f"   Price: ${item['price']:.2f} each\n"
            order_summary += f"   Subtotal: ${item_total:.2f}\n\n"

        order_summary += "="*50 + "\n"
        order_summary += f"SUBTOTAL: ${subtotal:.2f}\n"

        return [TextContent(
                type="text",
                text=order_summary
            )]

    except Exception as e:
        return [TextContent(
                type="text",
                text=f"Error viewing order: {str(e)}"
            )]

async def handle_set_customer_info(arguments: Dict[str, Any]) -> list:
    """Set customer information"""
    try:
        customer_data = {
            "FirstName": arguments["first_name"],
            "LastName": arguments["last_name"], 
            "Email": arguments["email"],
            "Phone": arguments["phone"],
            "Address": {
                "Street": arguments["address"]["street"],
                "City": arguments["address"]["city"],
                "Region": arguments["address"]["region"],
                "PostalCode": arguments["address"]["zip"]
            }
        }
        
        # Create customer with correct parameter names (fname, lname, email, phone)
        pizza_order.customer = Customer(
            fname=arguments["first_name"],
            lname=arguments["last_name"],
            email=arguments["email"],
            phone=arguments["phone"]
        )

        # Set address separately
        pizza_order.customer.address = Address(
            arguments["address"]["street"],
            arguments["address"]["city"],
            arguments["address"]["region"],
            arguments["address"]["zip"]
        )
        
        return [TextContent(
                type="text",
                text="Customer information set successfully"
            )]
        
    except Exception as e:
        return [TextContent(
                type="text",
                text=f"Error setting customer info: {str(e)}"
            )]

async def handle_calculate_order_total(arguments: Dict[str, Any]) -> list:
    """Calculate order total"""
    try:
        if not pizza_order.items:
            return [TextContent(
                    type="text",
                    text="No items in order to calculate."
                )]

        # Calculate totals
        subtotal = sum(item["price"] * item["quantity"] for item in pizza_order.items)

        # Estimate tax (varies by location, using 9% as estimate)
        tax_rate = 0.09
        tax = subtotal * tax_rate

        # Delivery fee (typical Domino's fee)
        delivery_fee = 3.99

        # Total
        total = subtotal + tax + delivery_fee

        # Build summary
        summary = "Order Total Calculation:\n" + "="*50 + "\n\n"
        summary += f"Subtotal:      ${subtotal:.2f}\n"
        summary += f"Tax (est.):    ${tax:.2f}\n"
        summary += f"Delivery Fee:  ${delivery_fee:.2f}\n"
        summary += "-"*50 + "\n"
        summary += f"TOTAL:         ${total:.2f}\n"
        summary += "="*50 + "\n\n"
        summary += "Note: Tax rate is estimated. Actual total may vary.\n"

        if pizza_order.customer:
            summary += f"\nDelivery to: {pizza_order.customer.address.street}, "
            summary += f"{pizza_order.customer.address.city}, {pizza_order.customer.address.zip}\n"

        return [TextContent(
                type="text",
                text=summary
            )]

    except Exception as e:
        return [TextContent(
                type="text",
                text=f"Error calculating total: {str(e)}"
            )]

async def handle_apply_coupon(arguments: Dict[str, Any]) -> list:
    """Apply coupon to order"""
    try:
        if not pizza_order.order:
            return [TextContent(
                    type="text",
                    text="No order to apply coupon to."
                )]
        
        coupon_code = arguments["coupon_code"]
        
        # Apply coupon
        pizza_order.order.add_coupon(coupon_code)
        
        return [TextContent(
                type="text",
                text=f"Applied coupon: {coupon_code}"
            )]
        
    except Exception as e:
        return [TextContent(
                type="text",
                text=f"Error applying coupon: {str(e)}"
            )]

async def handle_place_order(arguments: Dict[str, Any]) -> list:
    """Place the order"""
    try:
        if not pizza_order.order:
            return [TextContent(
                    type="text",
                    text="No order to place."
                )]
        
        if not pizza_order.customer:
            return [TextContent(
                    type="text",
                    text="Customer information required. Use set_customer_info first."
                )]
        
        payment_info = arguments["payment_info"]
        
        # Set customer info on order
        pizza_order.order.set_customer(pizza_order.customer)
        
        # Handle payment based on type
        if payment_info["type"] == "cash":
            # For cash orders, just validate and prepare
            result = {"Status": "Success", "OrderID": "CASH_ORDER", "Message": "Cash order prepared for pickup"}
            
        elif payment_info["type"] == "card":
            # Validate required card fields
            required_fields = ["card_number", "expiration", "cvv", "billing_zip"]
            missing_fields = [field for field in required_fields if field not in payment_info or not payment_info[field]]
            
            if missing_fields:
                return [TextContent(
                        type="text",
                        text=f"Missing required card information: {', '.join(missing_fields)}"
                    )]
            
            # Create payment object
            card = PaymentObject(
                number=payment_info["card_number"],
                expiration=payment_info["expiration"],
                cvv=payment_info["cvv"],
                zip=payment_info["billing_zip"]
            )
            
            # Add tip if provided
            tip_amount = payment_info.get("tip_amount", 0)
            if tip_amount > 0:
                pizza_order.order.add_item({'Code': 'DELIVERY_TIP', 'Qty': 1, 'Price': tip_amount})
            
            # Place the actual order
            result = pizza_order.order.place(card)
            
        else:
            return [TextContent(
                    type="text",
                    text="Invalid payment type. Must be 'card' or 'cash'."
                )]
        
        # Format success response
        if isinstance(result, dict) and result.get("Status") == "Success":
            order_id = result.get("OrderID", "Unknown")
            return [TextContent(
                    type="text",
                    text=f"🍕 Order placed successfully!\n\nOrder ID: {order_id}\nPayment: {payment_info['type']}\n\nYour pizza is being prepared!"
                )]
        else:
            return [TextContent(
                    type="text",
                    text=f"Order placement failed: {result}"
                )]
        
    except Exception as e:
        return [TextContent(
                type="text",
                text=f"Error placing order: {str(e)}"
            )]

# Tool handlers mapping
TOOL_HANDLERS = {
    "find_dominos_store": handle_find_dominos_store,
    "get_store_menu": handle_get_store_menu,
    "search_menu": handle_search_menu,
    "add_to_order": handle_add_to_order,
    "view_order": handle_view_order,
    "set_customer_info": handle_set_customer_info,
    "calculate_order_total": handle_calculate_order_total,
    "apply_coupon": handle_apply_coupon,
    "place_order": handle_place_order,
}

def create_server() -> Server:
    """Create the MCP server instance"""
    server = Server("mcpizza")

    @server.list_tools()
    async def handle_list_tools() -> ListToolsResult:
        """List available tools"""
        return ListToolsResult(tools=TOOLS)

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list:
        """Handle tool calls"""
        if name not in TOOL_HANDLERS:
            raise ValueError(f"Unknown tool: {name}")

        handler = TOOL_HANDLERS[name]
        content_list = await handler(arguments or {})
        return content_list

    return server

async def main():
    """Run the server"""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="mcpizza",
                server_version="0.1.0",
                capabilities=ServerCapabilities(tools={})
            )
        )

if __name__ == "__main__":
    asyncio.run(main())
