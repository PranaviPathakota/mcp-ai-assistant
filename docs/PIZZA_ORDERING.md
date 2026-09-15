# Pizza Ordering

The assistant supports two pizza ordering modes: **browser automation** (any site) and **Domino's API** (via MCPizza).

## Mode 1: Browser Automation

Uses Playwright MCP + DuckDuckGo to autonomously navigate any pizza website.

### How It Works

1. User says "order pizza"
2. Assistant searches for pizza places near a given city
3. User selects a restaurant from the list
4. User provides delivery details (address, phone, name)
5. Assistant opens the site in a browser and fills in forms automatically
6. **Stops before payment** (safety feature — user completes checkout manually)

### Example Session

```
You: order pizza

Pizza Ordering Assistant
━━━━━━━━━━━━━━━━━━━━━━━━

Location for delivery? College Station, TX

Searching for pizza places near College Station, TX...

Found 5 pizza places:
  1. Domino's Pizza - College Station
  2. Pizza Hut - College Station
  ...

Which restaurant? (1-5): 1

Delivery address: 123 University Dr, Apt 2
Phone: 555-123-4567
Name: Jane Doe

Proceed with browser automation? (yes/no): yes

Opening Domino's Pizza website...
  Clicked 'Order Now' button
  Filled address field
  Filled phone field
  Clicked 'Continue'

Stopped before payment — complete the order manually in the browser.
```

### Autonomous Element Detection

The browser agent uses text-based selectors (more reliable than CSS selectors):

```python
# Tries multiple button text patterns
for button_text in ['Order Now', 'Start Order', 'Order', 'Delivery']:
    click_result = await mcp_client.call_tool('browser_click', {
        'selector': f'text={button_text}'
    })

# Tries multiple field selectors
for selector in [
    'input[name="address"]',
    'input[placeholder*="address" i]',
    'input[id*="address" i]',
]:
    await mcp_client.call_tool('browser_fill', {
        'selector': selector,
        'value': delivery_address
    })
```

## Mode 2: Domino's API (MCPizza)

Communicates directly with Domino's via the `pizzapi` Python library — no browser needed.

### Workflow

```
find_dominos_store  →  search_menu  →  add_to_order
      →  set_customer_info  →  calculate_order_total  →  place_order
```

### Example

```
You: order pizza from dominos

Street address: 123 Main St
City: College Station
State: TX
ZIP: 77840
Phone: 555-123-4567
Name: Jane Doe
Email: jane@example.com

Finding nearest Domino's store...
Store: #1234 - 456 College Ave, College Station TX

What pizza? pepperoni
Size? large

Searching menu for 'pepperoni'...
  Found: Pepperoni Pizza (S_PIZZA) — $12.99

Added 1x Pepperoni Pizza to order.

Order total: $12.99 + $1.17 tax + $3.99 delivery = $18.15

Proceed to checkout? (yes/no): yes
```

## Safety Features

- Browser automation always stops before the payment page
- MCPizza's `place_order` tool requires explicit confirmation
- Screenshots are taken at key steps for debugging
