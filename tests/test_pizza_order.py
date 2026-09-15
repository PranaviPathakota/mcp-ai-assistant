#!/usr/bin/env python3
"""
Test script for Domino's pizza ordering via mcpizza MCP server
This demonstrates the complete ordering flow without placing the actual order
"""

import asyncio
import sys
import os

# Add mcpizza to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mcpizza'))

from mcpizza.server import (
    handle_find_dominos_store,
    handle_search_menu,
    handle_add_to_order,
    handle_view_order,
    handle_set_customer_info,
    handle_calculate_order_total
)


async def test_pizza_ordering():
    """Test the complete pizza ordering flow"""

    print("\n" + "="*60)
    print("🍕 DOMINO'S PIZZA ORDERING TEST")
    print("="*60)

    # Step 1: Find a store
    print("\n[1] Finding Domino's store near ZIP code 94040...")
    store_result = await handle_find_dominos_store({"address": "94040"})
    print(f"✅ {store_result[0].text}\n")

    # Extract store_id from the result
    import json
    store_text = store_result[0].text
    store_data = json.loads(store_text.split("Found Domino's store:\n")[1])
    store_id = store_data["store_id"]
    print(f"📍 Using Store ID: {store_id}")

    # Step 2: Search for pizza
    print("\n[2] Searching for pepperoni pizza...")
    search_result = await handle_search_menu({
        "query": "pepperoni",
        "store_id": store_id
    })
    print(f"✅ {search_result[0].text[:500]}...\n")

    # Extract first item code
    search_text = search_result[0].text
    items = json.loads(search_text.split("Found ")[1].split(" items:\n")[1])
    if items:
        first_item = items[0]
        item_code = first_item["code"]
        item_name = first_item["name"]
        print(f"📦 Selected item: {item_name} (Code: {item_code})")
    else:
        print("❌ No items found")
        return

    # Step 3: Add item to order
    print(f"\n[3] Adding 1x {item_name} to order...")
    add_result = await handle_add_to_order({
        "item_code": item_code,
        "quantity": 1
    })
    print(f"✅ {add_result[0].text}")

    # Step 4: View order
    print("\n[4] Viewing current order...")
    view_result = await handle_view_order({})
    print(f"✅ {view_result[0].text[:300]}...")

    # Step 5: Set customer info
    print("\n[5] Setting customer information...")
    customer_result = await handle_set_customer_info({
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "phone": "555-123-4567",
        "address": {
            "street": "123 Test St",
            "city": "Mountain View",
            "region": "CA",
            "zip": "94040"
        }
    })
    print(f"✅ {customer_result[0].text}")

    # Step 6: Calculate total
    print("\n[6] Calculating order total...")
    total_result = await handle_calculate_order_total({})
    print(f"✅ {total_result[0].text}")

    print("\n" + "="*60)
    print("✅ PIZZA ORDER TEST COMPLETED SUCCESSFULLY!")
    print("="*60)
    print("\n⚠️  IMPORTANT:")
    print("   - Order was prepared but NOT placed")
    print("   - This is a demonstration of the API functionality")
    print("   - To place a real order, use the place_order tool")
    print("   - Payment information would be required for real orders")
    print("="*60 + "\n")


async def interactive_order():
    """Interactive pizza ordering demo"""

    print("\n" + "="*60)
    print("🍕 INTERACTIVE DOMINO'S PIZZA ORDERING")
    print("="*60)

    # Get address
    address = input("\n📍 Enter your ZIP code or address: ").strip()

    # Step 1: Find store
    print(f"\n🔍 Finding nearest Domino's to {address}...")
    store_result = await handle_find_dominos_store({"address": address})
    print(store_result[0].text)

    # Extract store_id
    import json
    try:
        store_text = store_result[0].text
        if "No Domino's stores found" in store_text:
            print("❌ No stores found. Please try a different address.")
            return

        store_data = json.loads(store_text.split("Found Domino's store:\n")[1])
        store_id = store_data["store_id"]
        print(f"\n✅ Using Store ID: {store_id}")
    except Exception as e:
        print(f"❌ Error parsing store data: {e}")
        return

    # Step 2: Search menu
    search_query = input("\n🔍 What would you like to search for? (e.g., pepperoni, cheese, wings): ").strip()

    print(f"\n🔍 Searching for '{search_query}'...")
    search_result = await handle_search_menu({
        "query": search_query,
        "store_id": store_id
    })
    print(search_result[0].text)

    # Parse search results
    try:
        search_text = search_result[0].text
        if "No items found" in search_text:
            print("\n❌ No items found. Try a different search term.")
            return

        items = json.loads(search_text.split("Found ")[1].split(" items:\n")[1])

        # Display items with numbers
        print("\n📋 Available items:")
        for i, item in enumerate(items[:10], 1):  # Show max 10 items
            print(f"   {i}. {item['name']} - ${item.get('price', 'N/A')} (Code: {item['code']})")

        # Get user selection
        choice = input("\n🛒 Enter item number to add (or 0 to skip): ").strip()

        if choice == "0":
            print("Skipping item selection...")
            return

        item_index = int(choice) - 1
        if item_index < 0 or item_index >= len(items):
            print("❌ Invalid selection")
            return

        selected_item = items[item_index]
        item_code = selected_item["code"]
        item_name = selected_item["name"]

        # Get quantity
        quantity = input(f"\n📦 How many {item_name}? (default 1): ").strip() or "1"

        # Add to order
        print(f"\n➕ Adding {quantity}x {item_name}...")
        add_result = await handle_add_to_order({
            "item_code": item_code,
            "quantity": int(quantity)
        })
        print(add_result[0].text)

        # View order
        print("\n📦 Current order:")
        view_result = await handle_view_order({})
        print(view_result[0].text)

        # Get customer info
        print("\n👤 Customer Information:")
        first_name = input("   First name: ").strip()
        last_name = input("   Last name: ").strip()
        email = input("   Email: ").strip()
        phone = input("   Phone (e.g., 555-123-4567): ").strip()
        street = input("   Street address: ").strip()
        city = input("   City: ").strip()
        state = input("   State (e.g., CA, NY): ").strip()
        zip_code = input("   ZIP code: ").strip()

        # Set customer info
        print("\n📝 Setting customer information...")
        customer_result = await handle_set_customer_info({
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "address": {
                "street": street,
                "city": city,
                "region": state,
                "zip": zip_code
            }
        })
        print(customer_result[0].text)

        # Calculate total
        print("\n💰 Calculating order total...")
        total_result = await handle_calculate_order_total({})
        print(total_result[0].text)

        print("\n" + "="*60)
        print("✅ ORDER PREPARED SUCCESSFULLY!")
        print("="*60)
        print("\n⚠️  IMPORTANT:")
        print("   - Your order is ready for review")
        print("   - Order was NOT placed (safety mode)")
        print("   - To place the order, you would use the place_order tool")
        print("   - This is a demonstration of the Domino's API")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n🍕 Domino's Pizza Ordering Demo")
    print("=" * 60)
    print("1. Automated test with sample data")
    print("2. Interactive ordering")
    print("=" * 60)

    choice = input("\nSelect mode (1 or 2): ").strip()

    if choice == "1":
        asyncio.run(test_pizza_ordering())
    elif choice == "2":
        asyncio.run(interactive_order())
    else:
        print("Invalid choice. Exiting.")
