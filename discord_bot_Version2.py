import discord
from discord.ext import commands, tasks
import asyncio
import random
import httpx

intents = discord.Intents.default()
intents.message_content = True

BACKEND_URL = "http://127.0.0.1:8000"

user_states = {}

bot = commands.Bot(command_prefix="!", intents=intents)

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

async def post_order_to_backend(state, discord_id, discord_name):
    order_data = {
        "id": 0,
        "tg_id": discord_id,
        "tg_username": discord_name,
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

# --- SUPPORT API HELPERS (same as before, with discord_id) ---
async def create_support_ticket(discord_id, discord_name, message):
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{BACKEND_URL}/support/ticket",
            json={"tg_id": discord_id, "tg_username": discord_name, "message": message}
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

# --- UI HELPERS ---

def basket_text(uid):
    basket = user_states[uid].get("basket", [])
    if not basket:
        return "**Your cart is empty.**"
    lines = ["**Your Cart:**"]
    total = 0
    for i, item in enumerate(basket, 1):
        lines.append(f"{i}. {item['name']} x{item['qty']} — £{item['qty']*item['price']:.2f}")
        total += item['qty']*item['price']
    lines.append(f"\n**Total: £{total:.2f}**")
    return "\n".join(lines)

def checkout_text(uid):
    state = user_states[uid]
    basket = state.get("basket", [])
    order_number = state.get("order_number") or random.randint(3000, 9999)
    state["order_number"] = order_number
    lines = [
        f"**Order #{order_number}**",
        "**Status:** ⏳ Checkout Progress",
        f"{'✅' if state.get('discount') else '➖'} Discount / "
        f"{'✅' if state.get('payment') else '➖'} Payment / "
        f"{'✅' if state.get('address') else '➖'} Address / "
        f"{'✅' if state.get('delivery') else '➖'} Delivery",
        "",
        "**Your Cart:**"
    ]
    total = 0
    for i, item in enumerate(basket, 1):
        lines.append(f"{i}. {item['name']} x{item['qty']} — £{item['qty']*item['price']:.2f}")
        total += item['qty']*item['price']
    lines.append(f"**Total: £{total:.2f}**")
    return "\n".join(lines)

def payment_screen(uid):
    state = user_states[uid]
    total = sum(item['qty'] * item['price'] for item in state.get("basket", []))
    addr = "bc1qexampleaddress"
    return (
        f"**Payment**\nSend **£{total:.2f}** in `{state.get('payment','Bitcoin')}` to:\n"
        f"`{addr}`\n\nAfter payment, press the button below to confirm."
    )

# --- BUTTONS & VIEWS ---

class HomeView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=None)
        self.uid = uid

    @discord.ui.button(label="🛍 Shop", custom_id="shop", style=discord.ButtonStyle.primary)
    async def shop(self, interaction, button):
        categories = await get_categories()
        await interaction.response.edit_message(content="**Shop Categories:**", view=ListingsView(self.uid, categories))

    @discord.ui.button(label="📦 Cart", custom_id="cart", style=discord.ButtonStyle.secondary)
    async def cart(self, interaction, button):
        await interaction.response.edit_message(content=basket_text(self.uid), view=BasketView(self.uid))

    @discord.ui.button(label="⭐ Reviews", custom_id="reviews", style=discord.ButtonStyle.secondary)
    async def reviews(self, interaction, button):
        await interaction.response.edit_message(content="⭐ **Reviews**\n\n4.90 (49 reviews)\n\n\"Super fast!\" - K.J.\n\"Best prices.\" - M.L.", view=InfoBackView(self.uid))

    @discord.ui.button(label="❓ FAQ", custom_id="faq", style=discord.ButtonStyle.secondary)
    async def faq(self, interaction, button):
        await interaction.response.edit_message(content="❓ **FAQ**\n\nQ: How does this work?\nA: Browse, add to cart, checkout. Codes delivered instantly!\nQ: Is delivery anonymous?\nA: Yes, always.", view=InfoBackView(self.uid))

    @discord.ui.button(label="🔑 PGP", custom_id="pgp", style=discord.ButtonStyle.secondary)
    async def pgp(self, interaction, button):
        await interaction.response.edit_message(content="🔑 **PGP Public Key**\n\n```\n-----BEGIN PGP PUBLIC KEY BLOCK-----\n...\n-----END PGP PUBLIC KEY BLOCK-----\n```", view=InfoBackView(self.uid))

    @discord.ui.button(label="💬 Support", custom_id="support", style=discord.ButtonStyle.danger)
    async def support(self, interaction, button):
        state = user_states[self.uid]
        if state.get("support_chat"):
            ticket_id = state["support_chat"]["ticket_id"]
            await interaction.response.edit_message(content="You already have an open support chat. Click below to continue or close.", view=SupportChatView(self.uid, ticket_id))
            return
        ticket = await create_support_ticket(self.uid, interaction.user.name, "User started support chat")
        state["support_chat"] = {"ticket_id": ticket["id"], "last_seen": len(ticket["messages"])}
        await interaction.response.edit_message(content="Support chat started! Click below to send a message or close the chat.", view=SupportChatView(self.uid, ticket["id"]))

class ListingsView(discord.ui.View):
    def __init__(self, uid, categories):
        super().__init__(timeout=None)
        self.uid = uid
        for cat in categories:
            self.add_item(ListingButton(uid, cat))
        self.add_item(BackHomeButton(uid))

class ListingButton(discord.ui.Button):
    def __init__(self, uid, cat):
        super().__init__(label=cat["name"], style=discord.ButtonStyle.primary, custom_id=f"cat_{cat['id']}")
        self.uid = uid
        self.cat_id = cat["id"]

    async def callback(self, interaction):
        products = await get_products_by_cat(self.cat_id)
        await interaction.response.edit_message(content="**Products in this category:**", view=ProductsView(self.uid, self.cat_id, products))

class ProductsView(discord.ui.View):
    def __init__(self, uid, cat_id, products):
        super().__init__(timeout=None)
        self.uid = uid
        self.cat_id = cat_id
        for p in products:
            self.add_item(ProductButton(uid, cat_id, p))
        self.add_item(ListingsBackButton(uid))

class ProductButton(discord.ui.Button):
    def __init__(self, uid, cat_id, prod):
        super().__init__(label=prod["name"], style=discord.ButtonStyle.primary, custom_id=f"prod_{cat_id}_{prod['id']}")
        self.uid = uid
        self.cat_id = cat_id
        self.prod = prod

    async def callback(self, interaction):
        qty = 1
        desc = self.prod["description"] or ""
        text = f"**{self.prod['name']}**\n\n{desc}\n\n**from £{self.prod['price']:.2f}**"
        await interaction.response.edit_message(content=text, view=ProdPageView(self.uid, self.cat_id, self.prod, qty))

class ProdPageView(discord.ui.View):
    def __init__(self, uid, cat_id, prod, qty):
        super().__init__(timeout=None)
        self.uid = uid
        self.cat_id = cat_id
        self.prod = prod
        self.qty = qty
        self.add_item(IncQtyButton(uid, cat_id, prod, qty))
        self.add_item(QtyDisplay(qty))
        self.add_item(DecQtyButton(uid, cat_id, prod, qty))
        self.add_item(AddCartButton(uid, cat_id, prod, qty))
        self.add_item(ProductBackButton(uid, cat_id))

class IncQtyButton(discord.ui.Button):
    def __init__(self, uid, cat_id, prod, qty):
        super().__init__(label="▲", style=discord.ButtonStyle.secondary, custom_id=f"incqty_{cat_id}_{prod['id']}_{qty+1}")
        self.uid = uid
        self.cat_id = cat_id
        self.prod = prod
        self.qty = qty

    async def callback(self, interaction):
        qty = self.qty + 1
        desc = self.prod["description"] or ""
        text = f"**{self.prod['name']}**\n\n{desc}\n\n**from £{self.prod['price']:.2f}**"
        await interaction.response.edit_message(content=text, view=ProdPageView(self.uid, self.cat_id, self.prod, qty))

class DecQtyButton(discord.ui.Button):
    def __init__(self, uid, cat_id, prod, qty):
        q = max(1, qty-1)
        super().__init__(label="▼", style=discord.ButtonStyle.secondary, custom_id=f"decqty_{cat_id}_{prod['id']}_{q}")
        self.uid = uid
        self.cat_id = cat_id
        self.prod = prod
        self.qty = q

    async def callback(self, interaction):
        qty = self.qty
        desc = self.prod["description"] or ""
        text = f"**{self.prod['name']}**\n\n{desc}\n\n**from £{self.prod['price']:.2f}**"
        await interaction.response.edit_message(content=text, view=ProdPageView(self.uid, self.cat_id, self.prod, qty))

class QtyDisplay(discord.ui.Button):
    def __init__(self, qty):
        super().__init__(label=f"Qty: {qty}", disabled=True, style=discord.ButtonStyle.grey)

class AddCartButton(discord.ui.Button):
    def __init__(self, uid, cat_id, prod, qty):
        super().__init__(label="🛒 Add to Cart", style=discord.ButtonStyle.success, custom_id=f"addcart_{cat_id}_{prod['id']}_{qty}")
        self.uid = uid
        self.cat_id = cat_id
        self.prod = prod
        self.qty = qty

    async def callback(self, interaction):
        state = user_states[self.uid]
        item = {"name": self.prod["name"], "qty": self.qty, "price": self.prod["price"]}
        state.setdefault("basket", []).append(item)
        await interaction.response.edit_message(content=f"✅ **Added {self.qty} x {self.prod['name']} to your cart.**\n\n{basket_text(self.uid)}", view=BasketView(self.uid))

class ProductBackButton(discord.ui.Button):
    def __init__(self, uid, cat_id):
        super().__init__(label="⬅️ Back", style=discord.ButtonStyle.secondary, custom_id=f"cat_{cat_id}")
        self.uid = uid
        self.cat_id = cat_id

    async def callback(self, interaction):
        products = await get_products_by_cat(self.cat_id)
        await interaction.response.edit_message(content="**Products in this category:**", view=ProductsView(self.uid, self.cat_id, products))

class ListingsBackButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="⬅️ Categories", style=discord.ButtonStyle.secondary, custom_id="listings")
        self.uid = uid

    async def callback(self, interaction):
        categories = await get_categories()
        await interaction.response.edit_message(content="**Shop Categories:**", view=ListingsView(self.uid, categories))

class BasketView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=None)
        self.uid = uid
        self.add_item(BasketRefreshButton(uid))
        self.add_item(BasketClearButton(uid))
        self.add_item(BasketCheckoutButton(uid))
        self.add_item(BasketHomeButton(uid))

class BasketRefreshButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="🔄 Update", style=discord.ButtonStyle.primary, custom_id="basket_refresh")
        self.uid = uid

    async def callback(self, interaction):
        await interaction.response.edit_message(content=basket_text(self.uid), view=BasketView(self.uid))

class BasketClearButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="🗑 Empty", style=discord.ButtonStyle.danger, custom_id="clear_basket")
        self.uid = uid

    async def callback(self, interaction):
        user_states[self.uid]["basket"] = []
        await interaction.response.edit_message(content="**Cart emptied!**", view=BasketView(self.uid))

class BasketCheckoutButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="✅ Checkout", style=discord.ButtonStyle.success, custom_id="checkout")
        self.uid = uid

    async def callback(self, interaction):
        state = user_states[self.uid]
        if not state.get("basket"):
            await interaction.response.edit_message(content="**Your cart is empty.**", view=HomeView(self.uid))
            return
        await interaction.response.edit_message(content=checkout_text(self.uid), view=CheckoutView(self.uid))

class BasketHomeButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="⬅️ Home", style=discord.ButtonStyle.secondary, custom_id="home")
        self.uid = uid

    async def callback(self, interaction):
        await interaction.response.edit_message(content="👋 **Welcome to Giftly Unique!**\nUse the menu below to start shopping.", view=HomeView(self.uid))

class CheckoutView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=None)
        self.uid = uid
        state = user_states[uid]
        self.add_item(CheckoutDiscountButton(uid))
        self.add_item(CheckoutPaymentButton(uid))
        self.add_item(CheckoutAddressButton(uid))
        self.add_item(CheckoutDeliveryButton(uid))
        self.add_item(CheckoutBackButton(uid))
        self.add_item(CheckoutCancelButton(uid))
        self.add_item(CheckoutConfirmButton(uid))

class CheckoutDiscountButton(discord.ui.Button):
    def __init__(self, uid):
        state = user_states[uid]
        label = ("✅" if state.get("discount") else "➖") + " Discount"
        super().__init__(label=label, style=discord.ButtonStyle.secondary, custom_id="checkout_discount")
        self.uid = uid

    async def callback(self, interaction):
        await interaction.response.send_message("🎟️ **Reply with your discount code:**", ephemeral=True)
        user_states[self.uid]["awaiting_discount"] = True

class CheckoutPaymentButton(discord.ui.Button):
    def __init__(self, uid):
        state = user_states[uid]
        label = ("✅" if state.get("payment") else "➖") + " Payment"
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id="checkout_payment")
        self.uid = uid

    async def callback(self, interaction):
        await interaction.response.edit_message(content="💳 **Pick a payment method:**", view=PaymentView(self.uid))

class CheckoutAddressButton(discord.ui.Button):
    def __init__(self, uid):
        state = user_states[uid]
        label = ("✅" if state.get("address") else "➖") + " Address"
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id="checkout_address")
        self.uid = uid

    async def callback(self, interaction):
        await interaction.response.send_message("🏡 **Reply with your delivery address:**", ephemeral=True)
        user_states[self.uid]["awaiting_address"] = True

class CheckoutDeliveryButton(discord.ui.Button):
    def __init__(self, uid):
        state = user_states[uid]
        label = ("✅" if state.get("delivery") else "➖") + " Delivery"
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id="checkout_delivery")
        self.uid = uid

    async def callback(self, interaction):
        delivery_methods = await get_delivery_methods()
        await interaction.response.edit_message(content="🚚 **Pick a delivery method:**", view=DeliveryView(self.uid, delivery_methods))

class CheckoutBackButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="⬅️ Cart", style=discord.ButtonStyle.secondary, custom_id="basket")
        self.uid = uid

    async def callback(self, interaction):
        await interaction.response.edit_message(content=basket_text(self.uid), view=BasketView(self.uid))

class CheckoutCancelButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="cancel")
        self.uid = uid

    async def callback(self, interaction):
        for k in ["basket", "order_number", "payment", "delivery", "address", "discount"]:
            user_states[self.uid][k] = None
        await interaction.response.edit_message(content="❌ **Order cancelled.**", view=HomeView(self.uid))

class CheckoutConfirmButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="✅ Confirm & Pay", style=discord.ButtonStyle.success, custom_id="confirm")
        self.uid = uid

    async def callback(self, interaction):
        state = user_states[self.uid]
        if not (state.get("payment") and state.get("address") and state.get("delivery")):
            await interaction.response.send_message("Please complete all steps!", ephemeral=True)
            return
        await interaction.response.edit_message(content=payment_screen(self.uid), view=ConfirmPaymentView(self.uid))

class PaymentView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=None)
        self.uid = uid
        for m in ["Bitcoin", "Litecoin", "Monero"]:
            self.add_item(PaymentMethodButton(uid, m))
        self.add_item(CheckoutBackButton(uid))

class PaymentMethodButton(discord.ui.Button):
    def __init__(self, uid, m):
        super().__init__(label=m, style=discord.ButtonStyle.primary, custom_id=f"pay_{m}")
        self.uid = uid
        self.m = m

    async def callback(self, interaction):
        state = user_states[self.uid]
        state["payment"] = self.m
        await interaction.response.edit_message(content=checkout_text(self.uid), view=CheckoutView(self.uid))

class DeliveryView(discord.ui.View):
    def __init__(self, uid, methods):
        super().__init__(timeout=None)
        self.uid = uid
        for m in methods:
            self.add_item(DeliveryMethodButton(uid, m))
        self.add_item(CheckoutBackButton(uid))

class DeliveryMethodButton(discord.ui.Button):
    def __init__(self, uid, m):
        super().__init__(label=m["name"], style=discord.ButtonStyle.primary, custom_id=f"del_{m['id']}")
        self.uid = uid
        self.m = m

    async def callback(self, interaction):
        state = user_states[self.uid]
        state["delivery"] = self.m["name"]
        await interaction.response.edit_message(content=checkout_text(self.uid), view=CheckoutView(self.uid))

class ConfirmPaymentView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=None)
        self.uid = uid
        self.add_item(PaidConfirmedButton(uid))
        self.add_item(CheckoutCancelButton(uid))

class PaidConfirmedButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="✅ I have paid", style=discord.ButtonStyle.success, custom_id="paid_confirmed")
        self.uid = uid

    async def callback(self, interaction):
        sender = interaction.user
        state = user_states[self.uid]
        order = await post_order_to_backend(
            state, self.uid, sender.name
        )
        async with httpx.AsyncClient() as c:
            await c.post(f"{BACKEND_URL}/order/{order['id']}/mark_paid")
        await interaction.response.edit_message(content="🎉 **Order confirmed! You'll receive your items soon.**", view=HomeView(self.uid))
        for k in ["basket", "order_number", "payment", "delivery", "address", "discount"]:
            state[k] = None

class InfoBackView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=None)
        self.uid = uid
        self.add_item(HomeBackButton(uid))

class HomeBackButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="⬅️ Home", style=discord.ButtonStyle.secondary, custom_id="home")
        self.uid = uid

    async def callback(self, interaction):
        await interaction.response.edit_message(content="👋 **Welcome to Giftly Unique!**\nUse the menu below to start shopping.", view=HomeView(self.uid))

class BackHomeButton(discord.ui.Button):
    def __init__(self, uid):
        super().__init__(label="⬅️ Home", style=discord.ButtonStyle.secondary, custom_id="home")
        self.uid = uid

    async def callback(self, interaction):
        await interaction.response.edit_message(content="👋 **Welcome to Giftly Unique!**\nUse the menu below to start shopping.", view=HomeView(self.uid))

# --- Support Views ---
class SupportChatView(discord.ui.View):
    def __init__(self, uid, ticket_id):
        super().__init__(timeout=None)
        self.uid = uid
        self.ticket_id = ticket_id
        self.add_item(SupportSendMessageButton(uid, ticket_id))
        self.add_item(SupportCloseButton(uid, ticket_id))

class SupportSendMessageButton(discord.ui.Button):
    def __init__(self, uid, ticket_id):
        super().__init__(label="📝 Send Message", style=discord.ButtonStyle.primary, custom_id=f"support_chat_{ticket_id}")
        self.uid = uid
        self.ticket_id = ticket_id

    async def callback(self, interaction):
        user_states[self.uid]["support_chat"]["awaiting"] = True
        await interaction.response.send_message("Send your message for support now. Type `/close` to end support.", ephemeral=True)

class SupportCloseButton(discord.ui.Button):
    def __init__(self, uid, ticket_id):
        super().__init__(label="❌ Close Chat", style=discord.ButtonStyle.danger, custom_id=f"support_close_{ticket_id}")
        self.uid = uid
        self.ticket_id = ticket_id

    async def callback(self, interaction):
        await close_support_ticket(self.ticket_id)
        user_states[self.uid]["support_chat"] = None
        await interaction.response.edit_message(content="Support chat closed.", view=HomeView(self.uid))

class SupportNewMsgView(discord.ui.View):
    def __init__(self, uid, ticket_id):
        super().__init__(timeout=None)
        self.uid = uid
        self.ticket_id = ticket_id
        self.add_item(SupportOpenMsgButton(uid, ticket_id))

class SupportOpenMsgButton(discord.ui.Button):
    def __init__(self, uid, ticket_id):
        super().__init__(label="Open message", style=discord.ButtonStyle.primary, custom_id=f"open_support_{ticket_id}")
        self.uid = uid
        self.ticket_id = ticket_id

    async def callback(self, interaction):
        ticket = await get_support_ticket(self.ticket_id)
        admin_msgs = [m["content"] for m in ticket["messages"] if m["sender"] == "admin"]
        if admin_msgs:
            await interaction.response.send_message(f"Seller: {admin_msgs[-1]}", ephemeral=True)
        else:
            await interaction.response.send_message("No message from seller yet.", ephemeral=True)

# --- COMMANDS & HANDLERS ---
@bot.event
async def on_ready():
    print(f"Bot running as {bot.user}")
    poller.start()

@bot.command()
async def start(ctx):
    uid = ctx.author.id
    if uid not in user_states:
        user_states[uid] = {"basket": []}
    await ctx.send("👋 **Welcome to Giftly Unique!**\nUse the menu below to start shopping.", view=HomeView(uid))

@bot.event
async def on_message(message):
    uid = message.author.id
    state = user_states.get(uid, {})
    if message.author == bot.user:
        return
    # Support Chat
    if state.get("support_chat"):
        ticket_id = state["support_chat"]["ticket_id"]
        if message.content.strip() == "/close":
            await close_support_ticket(ticket_id)
            state["support_chat"] = None
            await message.channel.send("Support chat closed.", view=HomeView(uid))
            return
        if state["support_chat"].get("awaiting") or True:
            await add_support_message(ticket_id, "customer", message.content)
            state["support_chat"]["awaiting"] = False
            await message.channel.send("Message sent to support. Await a reply.", delete_after=8)
        return
    if state.get("awaiting_discount"):
        state["discount"] = message.content.strip()
        state["awaiting_discount"] = False
        await message.channel.send(checkout_text(uid), view=CheckoutView(uid))
    elif state.get("awaiting_address"):
        state["address"] = message.content.strip()
        state["awaiting_address"] = False
        await message.channel.send(checkout_text(uid), view=CheckoutView(uid))
    else:
        await bot.process_commands(message)

# --- Poller: background notification for support and dispatch ---
@tasks.loop(seconds=3)
async def poller():
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
                user = bot.get_user(uid)
                if user:
                    await user.send("You have a new message from seller.", view=SupportNewMsgView(uid, ticket_id))
                state["support_chat"]["last_seen"] = len(ticket["messages"])
    dispatches = await get_dispatch_notifications()
    for note in dispatches:
        user = bot.get_user(note["tg_id"])
        if user:
            await user.send(note["message"])

if __name__ == "__main__":
    bot.run("MTM3NjYzODY0NzkzOTYzMzE5Mg.GfxSK-.HuxVoJ3tQp9RMoMNa_20aYOYWv1mmqxfVrX5wQ")