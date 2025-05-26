import asyncio
import random
import httpx
from telethon import TelegramClient, events, Button

API_ID = 24336862  # Your Telegram API ID
API_HASH = "015e7723d9458a0a6716f2e26594c3ed"
BOT_TOKEN = '7717366228:AAGwn04G6bMwwowA1GxLfKIPvgbuNlVmhp4'
BACKEND_URL = "http://127.0.0.1:8000"

user_states = {}

client = TelegramClient('shopbot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# --- API HELPERS ---

async def get_categories():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BACKEND_URL}/categories")
        return r.json()

async def get_products():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BACKEND_URL}/products")
        return r.json()

async def get_delivery_methods():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BACKEND_URL}/delivery_methods")
        return r.json()

async def get_products_by_cat(cat_id):
    all_products = await get_products()
    return [p for p in all_products if p["category_id"] == cat_id]

async def post_order_to_backend(state, tg_id, tg_username):
    order_data = {
        "id": 0,
        "tg_id": tg_id,
        "tg_username": tg_username,
        "address": state.get("address"),
        "products": state.get("basket", []),
        "delivery_method": state.get("delivery"),
        "payment_method": state.get("payment"),
        "paid": False,
        "dispatched": False,
    }
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BACKEND_URL}/orders", json=order_data)
        return r.json()

# --- SUPPORT API HELPERS ---

async def create_support_ticket(tg_id, tg_username, message):
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{BACKEND_URL}/support/ticket",
            json={"tg_id": tg_id, "tg_username": tg_username, "message": message}
        )
        return r.json()

async def add_support_message(ticket_id, sender, content):
    async with httpx.AsyncClient() as c:
        await c.post(
            f"{BACKEND_URL}/support/ticket/{ticket_id}/message",
            json={"sender": sender, "content": content}
        )

async def close_support_ticket(ticket_id):
    async with httpx.AsyncClient() as c:
        await c.post(f"{BACKEND_URL}/support/ticket/{ticket_id}/close")

async def get_support_ticket(ticket_id):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BACKEND_URL}/support/ticket/{ticket_id}")
        return r.json()

async def get_dispatch_notifications():
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BACKEND_URL}/dispatch_notifications")
        return r.json()

# --- BUTTONS ---

def home_btns():
    return [
        [Button.inline("🛍 Shop", b"listings"), Button.inline("📦 Cart", b"basket")],
        [Button.inline("⭐ Reviews", b"reviews"), Button.inline("❓ FAQ", b"faq")],
        [Button.inline("🔑 PGP", b"pgp"), Button.inline("💬 Support", b"support")],
    ]

def listings_btns(categories):
    btns = [[Button.inline(cat["name"], f"cat_{cat['id']}".encode())] for cat in categories]
    btns.append([Button.inline("⬅️ Home", b"home")])
    return btns

def prod_btns(products, cat_id):
    btns = [[Button.inline(p['name'], f"prod_{cat_id}_{p['id']}".encode())] for p in products]
    btns.append([Button.inline("⬅️ Categories", b"listings")])
    return btns

def prod_page_btns(cat_id, prod_id, qty):
    return [
        [Button.inline("▲", f"incqty_{cat_id}_{prod_id}_{qty+1}".encode())],
        [Button.inline(f"Qty: {qty}", b"noop")],
        [Button.inline("▼", f"decqty_{cat_id}_{prod_id}_{max(1, qty-1)}".encode())],
        [Button.inline("🛒 Add to Cart", f"addcart_{cat_id}_{prod_id}_{qty}".encode())],
        [Button.inline("⬅️ Back", f"cat_{cat_id}".encode())]
    ]

def basket_btns():
    return [
        [Button.inline("🔄 Update", b"basket_refresh"), Button.inline("🗑 Empty", b"clear_basket")],
        [Button.inline("✅ Checkout", b"checkout")],
        [Button.inline("⬅️ Home", b"home")]
    ]

def checkout_btns(uid):
    state = user_states[uid]
    return [
        [Button.inline(("✅" if state.get("discount") else "➖") + " Discount", b"checkout_discount"),
         Button.inline(("✅" if state.get("payment") else "➖") + " Payment", b"checkout_payment")],
        [Button.inline(("✅" if state.get("address") else "➖") + " Address", b"checkout_address"),
         Button.inline(("✅" if state.get("delivery") else "➖") + " Delivery", b"checkout_delivery")],
        [Button.inline("⬅️ Cart", b"basket"), Button.inline("❌ Cancel", b"cancel")],
        [Button.inline("✅ Confirm & Pay", b"confirm")]
    ]

def payment_btns():
    return [[Button.inline(m, f"pay_{m}".encode())] for m in ["Bitcoin", "Litecoin", "Monero"]] + [[Button.inline("⬅️ Checkout", b"checkout")]]

def delivery_btns(delivery_methods):
    return [[Button.inline(m["name"], f"del_{m['id']}".encode())] for m in delivery_methods] + [[Button.inline("⬅️ Checkout", b"checkout")]]

def confirm_payment_btns():
    return [
        [Button.inline("✅ I have paid", b"paid_confirmed")],
        [Button.inline("❌ Cancel", b"cancel")]
    ]

def info_back_btns():
    return [[Button.inline("⬅️ Home", b"home")]]

def support_chat_btns(ticket_id):
    return [[Button.inline("📝 Send Message", f"support_chat_{ticket_id}".encode())],
            [Button.inline("❌ Close Chat", f"support_close_{ticket_id}".encode())]]

def support_new_msg_btn(ticket_id):
    return [[Button.inline("Open message", f"open_support_{ticket_id}".encode())]]

# --- UI TEXTS ---

def basket_text(uid):
    basket = user_states[uid].get("basket", [])
    if not basket:
        return "<b>Your cart is empty.</b>"
    lines = ["<b>Your Cart:</b>"]
    total = 0
    for i, item in enumerate(basket, 1):
        lines.append(f"{i}. {item['name']} x{item['qty']} — £{item['qty']*item['price']:.2f}")
        total += item['qty']*item['price']
    lines.append(f"\n<b>Total: £{total:.2f}</b>")
    return "\n".join(lines)

def checkout_text(uid):
    state = user_states[uid]
    basket = state.get("basket", [])
    order_number = state.get("order_number") or random.randint(3000, 9999)
    state["order_number"] = order_number
    lines = [
        f"<b>Order #{order_number}</b>",
        "<b>Status:</b> ⏳ Checkout Progress",
        f"{'✅' if state.get('discount') else '➖'} Discount / "
        f"{'✅' if state.get('payment') else '➖'} Payment / "
        f"{'✅' if state.get('address') else '➖'} Address / "
        f"{'✅' if state.get('delivery') else '➖'} Delivery",
        "",
        "<b>Your Cart:</b>"
    ]
    total = 0
    for i, item in enumerate(basket, 1):
        lines.append(f"{i}. {item['name']} x{item['qty']} — £{item['qty']*item['price']:.2f}")
        total += item['qty']*item['price']
    lines.append(f"<b>Total: £{total:.2f}</b>")
    return "\n".join(lines)

def payment_screen(uid):
    state = user_states[uid]
    total = sum(item['qty'] * item['price'] for item in state.get("basket", []))
    addr = "bc1qexampleaddress"
    return (
        f"<b>Payment</b>\nSend <b>£{total:.2f}</b> in <code>{state.get('payment','Bitcoin')}</code> to:\n"
        f"<code>{addr}</code>\n\nAfter payment, press the button below to confirm."
    )

# --- MAIN BOT LOGIC ---

@client.on(events.NewMessage(pattern="/start"))
async def start(event):
    if user_states.get(event.sender_id):
        await event.respond(
            "👋 <b>Welcome to Giftly Unique!</b>\nUse the menu below to start shopping.",
            buttons=home_btns(),
            parse_mode="html"
        )
        return
    user_states[event.sender_id] = {"basket": []}
    await event.respond(
        "👋 <b>Welcome to Giftly Unique!</b>\nUse the menu below to start shopping.",
        buttons=home_btns(),
        parse_mode="html"
    )

@client.on(events.CallbackQuery)
async def handler(event):
    uid = event.sender_id
    if uid not in user_states:
        user_states[uid] = {"basket": []}
    state = user_states[uid]
    data = event.data.decode()

    # --- Support Chat Buttons ---
    if data == "support":
        if state.get("support_chat"):
            ticket_id = state["support_chat"]["ticket_id"]
            await event.respond("You already have an open support chat. Click below to continue or close.", buttons=support_chat_btns(ticket_id))
            return
        # Create ticket
        sender = await event.get_sender()
        ticket = await create_support_ticket(uid, getattr(sender, "username", None), "User started support chat")
        state["support_chat"] = {"ticket_id": ticket["id"], "last_seen": len(ticket["messages"])}
        await event.respond("Support chat started! Click below to send a message or close the chat.", buttons=support_chat_btns(ticket["id"]))
        return

    if data.startswith("support_chat_"):
        ticket_id = int(data.split("_")[-1])
        state["support_chat"]["awaiting"] = True
        await event.respond("Send your message for support now. Type /close to end support.")

    if data.startswith("support_close_"):
        ticket_id = int(data.split("_")[-1])
        await close_support_ticket(ticket_id)
        state["support_chat"] = None
        await event.respond("Support chat closed.", buttons=home_btns())
        return

    if data.startswith("open_support_"):
        ticket_id = int(data.split("_")[-1])
        ticket = await get_support_ticket(ticket_id)
        admin_msgs = [m["content"] for m in ticket["messages"] if m["sender"] == "admin"]
        if admin_msgs:
            await event.respond(f"Seller: {admin_msgs[-1]}")
        else:
            await event.respond("No message from seller yet.")
        return

    # --- Shop Logic ---
    if data == "home":
        await event.edit("👋 <b>Welcome to Giftly Unique!</b>\nUse the menu below to start shopping.",
                         buttons=home_btns(), parse_mode="html")
    elif data == "listings":
        categories = await get_categories()
        await event.edit("<b>Shop Categories:</b>", buttons=listings_btns(categories), parse_mode="html")
    elif data.startswith("cat_"):
        cat_id = int(data[4:])
        products = await get_products_by_cat(cat_id)
        await event.edit(f"<b>Products in this category:</b>",
                         buttons=prod_btns(products, cat_id), parse_mode="html")
    elif data.startswith("prod_"):
        _, cat_id, prod_id = data.split("_", 2)
        products = await get_products_by_cat(int(cat_id))
        prod = next((x for x in products if x["id"] == int(prod_id)), None)
        qty = 1
        desc = prod["description"] or ""
        await event.edit(f"<b>{prod['name']}</b>\n\n{desc}\n\n<b>from £{prod['price']:.2f}</b>",
                         buttons=prod_page_btns(int(cat_id), int(prod_id), qty), parse_mode="html")
    elif data.startswith("incqty_") or data.startswith("decqty_"):
        _, cat_id, prod_id, qty = data.split("_", 3)
        qty = int(qty)
        products = await get_products_by_cat(int(cat_id))
        prod = next((x for x in products if x["id"] == int(prod_id)), None)
        desc = prod["description"] or ""
        await event.edit(f"<b>{prod['name']}</b>\n\n{desc}\n\n<b>from £{prod['price']:.2f}</b>",
                         buttons=prod_page_btns(int(cat_id), int(prod_id), qty), parse_mode="html")
    elif data.startswith("addcart_"):
        _, cat_id, prod_id, qty = data.split("_", 3)
        qty = int(qty)
        products = await get_products_by_cat(int(cat_id))
        prod = next((x for x in products if x["id"] == int(prod_id)), None)
        item = {"name": prod["name"], "qty": qty, "price": prod["price"]}
        state.setdefault("basket", []).append(item)
        await event.edit(f"✅ <b>Added {qty} x {prod['name']} to your cart.</b>\n\n{basket_text(uid)}",
                         buttons=basket_btns(), parse_mode="html")
    elif data == "basket" or data == "basket_refresh":
        await event.edit(basket_text(uid), buttons=basket_btns(), parse_mode="html")
    elif data == "clear_basket":
        state["basket"] = []
        await event.edit("<b>Cart emptied!</b>", buttons=basket_btns(), parse_mode="html")
    elif data == "checkout":
        if not state.get("basket"):
            await event.edit("<b>Your cart is empty.</b>", buttons=home_btns(), parse_mode="html")
            return
        await event.edit(checkout_text(uid), buttons=checkout_btns(uid), parse_mode="html")
    elif data == "checkout_discount":
        await event.edit("🎟️ <b>Reply with your discount code:</b>", buttons=[Button.inline("⬅️ Checkout", b"checkout")], parse_mode="html")
        state["awaiting_discount"] = True
    elif data == "checkout_payment":
        await event.edit("💳 <b>Pick a payment method:</b>", buttons=payment_btns(), parse_mode="html")
    elif data == "checkout_address":
        await event.edit("🏡 <b>Reply with your delivery address:</b>", buttons=[Button.inline("⬅️ Checkout", b"checkout")], parse_mode="html")
        state["awaiting_address"] = True
    elif data == "checkout_delivery":
        delivery_methods = await get_delivery_methods()
        await event.edit("🚚 <b>Pick a delivery method:</b>", buttons=delivery_btns(delivery_methods), parse_mode="html")
    elif data.startswith("pay_"):
        pay = data[4:]
        state["payment"] = pay
        await event.edit(checkout_text(uid), buttons=checkout_btns(uid), parse_mode="html")
    elif data.startswith("del_"):
        del_id = int(data[4:])
        delivery_methods = await get_delivery_methods()
        d = next((x for x in delivery_methods if x["id"] == del_id), None)
        state["delivery"] = d["name"]
        await event.edit(checkout_text(uid), buttons=checkout_btns(uid), parse_mode="html")
    elif data == "confirm":
        if not (state.get("payment") and state.get("address") and state.get("delivery")):
            await event.answer("Please complete all steps!", alert=True)
            return
        await event.edit(payment_screen(uid),
                         buttons=confirm_payment_btns(),
                         parse_mode="html")
    elif data == "paid_confirmed":
        sender = await event.get_sender()
        order = await post_order_to_backend(
            state, uid, getattr(sender, "username", None)
        )
        # Mark order as paid
        async with httpx.AsyncClient() as c:
            await c.post(f"{BACKEND_URL}/order/{order['id']}/mark_paid")
        await event.edit("🎉 <b>Order confirmed! You'll receive your items soon.</b>",
                         buttons=home_btns(), parse_mode="html")
        for k in ["basket", "order_number", "payment", "delivery", "address", "discount"]:
            state[k] = None
    elif data == "cancel":
        await event.edit("❌ <b>Order cancelled.</b>", buttons=home_btns(), parse_mode="html")
        for k in ["basket", "order_number", "payment", "delivery", "address", "discount"]:
            state[k] = None
    elif data == "reviews":
        await event.edit("⭐ <b>Reviews</b>\n\n4.90 (49 reviews)\n\n\"Super fast!\" - K.J.\n\"Best prices.\" - M.L.",
                         buttons=info_back_btns(), parse_mode="html")
    elif data == "faq":
        await event.edit("❓ <b>FAQ</b>\n\nQ: How does this work?\nA: Browse, add to cart, checkout. Codes delivered instantly!\nQ: Is delivery anonymous?\nA: Yes, always.",
                         buttons=info_back_btns(), parse_mode="html")
    elif data == "pgp":
        await event.edit("🔑 <b>PGP Public Key</b>\n\n<code>-----BEGIN PGP PUBLIC KEY BLOCK-----\n...\n-----END PGP PUBLIC KEY BLOCK-----</code>",
                         buttons=info_back_btns(), parse_mode="html")
    else:
        await event.answer("Unknown action", alert=True)

@client.on(events.NewMessage)
async def catch_all(event):
    uid = event.sender_id
    state = user_states.get(uid, {})
    # --- Support Chat ---
    if state.get("support_chat"):
        ticket_id = state["support_chat"]["ticket_id"]
        if event.text == "/close":
            await close_support_ticket(ticket_id)
            state["support_chat"] = None
            await event.respond("Support chat closed.", buttons=home_btns())
            return
        # Only accept message if in chat mode or awaiting
        if state["support_chat"].get("awaiting") or True:
            await add_support_message(ticket_id, "customer", event.text)
            state["support_chat"]["awaiting"] = False
            await event.respond("Message sent to support. Await a reply.")
        return

    if state.get("awaiting_discount"):
        state["discount"] = event.text.strip()
        state["awaiting_discount"] = False
        await event.respond(checkout_text(uid), buttons=checkout_btns(uid), parse_mode="html")
    elif state.get("awaiting_address"):
        state["address"] = event.text.strip()
        state["awaiting_address"] = False
        await event.respond(checkout_text(uid), buttons=checkout_btns(uid), parse_mode="html")
    else:
        await event.respond("👋 <b>Welcome to Giftly Unique!</b>\nUse the menu below to start shopping.",
            buttons=home_btns(), parse_mode="html"
        )

# --- Support/Dispatch Poller: Notify customer when admin replies or order is dispatched ---
async def poller():
    while True:
        await asyncio.sleep(3)
        # Support notification
        for uid, state in user_states.items():
            if state.get("support_chat"):
                ticket_id = state["support_chat"]["ticket_id"]
                try:
                    ticket = await get_support_ticket(ticket_id)
                except Exception:
                    continue
                last_seen = state["support_chat"].get("last_seen", 0)
                new_msgs = ticket["messages"][last_seen:]
                unseen = [m for m in new_msgs if m["sender"] == "admin"]
                if unseen:
                    await client.send_message(uid, "You have a new message from seller.", buttons=support_new_msg_btn(ticket_id))
                    state["support_chat"]["last_seen"] = len(ticket["messages"])
        # Dispatch notification
        dispatches = await get_dispatch_notifications()
        for note in dispatches:
            await client.send_message(note["tg_id"], note["message"])

client.loop.create_task(poller())

if __name__ == "__main__":
    print("Bot running...")
    client.run_until_disconnected()