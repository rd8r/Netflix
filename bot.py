import os
import logging
import asyncio
import random
import string
import uuid

from threading import Thread
from datetime import datetime, timedelta

from flask import Flask

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.constants import ParseMode, ChatMemberStatus

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from pymongo import MongoClient

BOT_TOKEN   = os.environ.get("BOT_TOKEN", "8887949396:AAHLuO27vXt1I9WTD2VPgaHUBgFnCoBoRLU")
ADMIN_IDS   = [int(x) for x in os.environ.get("ADMIN_IDS", "8192070400").split(",")]
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "-1003863083143"))
MONGO_URL   = os.environ.get("MONGO_URL", "mongodb+srv://radheysun:Sunyourradhey%23123@cluster0.dwtcsv7.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
PORT        = int(os.environ.get("PORT", 10000))

CHANNELS = ["@xivasudev", "@incurseing"]

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "✅ Bot is Running"

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

mongo      = MongoClient(MONGO_URL)
db         = mongo["PremiumRedeemBot"]
users_col  = db["users"]
stocks_col = db["stocks"]
coupons_col= db["coupons"]
services_col= db["services"]

def is_admin(uid):
    return uid in ADMIN_IDS

async def get_points(uid):
    u = users_col.find_one({"user_id": uid})
    return u.get("points", 0) if u else 0

async def add_points(uid, amount):
    users_col.update_one({"user_id": uid}, {"$inc": {"points": amount}}, upsert=True)

async def remove_points(uid, amount):
    users_col.update_one({"user_id": uid}, {"$inc": {"points": -amount}})

async def check_join(bot, uid):
    for ch in CHANNELS:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                return False
        except:
            return False
    return True

def gen_coupon_code():
    part1 = ''.join(random.choices(string.ascii_uppercase, k=6))
    part2 = ''.join(random.choices(string.digits, k=6))
    part3 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    part4 = uuid.uuid4().hex[:6].upper()
    return f"RADHEY-{part1}-{part2}-{part3}-{part4}"

def md(text):
    return str(text).replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")

async def log(bot, text):
    try:
        await bot.send_message(LOG_CHANNEL, text, parse_mode=ParseMode.MARKDOWN)
    except:
        pass

async def send_start(update, context, user):
    uid = user.id
    points = await get_points(uid)

    services = list(services_col.find({}))

    service_lines = ""
    for s in services:
        stock_count = stocks_col.count_documents({"service": s["name"], "redeemed": False})
        inr_price = s.get("inr_price", "N/A")
        pts_cost  = s.get("points_cost", "N/A")
        service_lines += f"  ┣ **{s['name']}** ─ 💰 {pts_cost} pts  ₹{inr_price}  📦 {stock_count}\n"

    if not service_lines:
        service_lines = "  ┗ _No services added yet_\n"

    text = (
        f"╔══════════════════════════╗\n"
        f"       🌟 **PREMIUM REDEEM BOT** 🌟\n"
        f"╚══════════════════════════╝\n\n"
        f"👤 **Name :** {md(user.first_name)}\n"
        f"🆔 **User ID :** `{uid}`\n"
        f"📛 **Username :** @{md(user.username or 'N/A')}\n"
        f"💰 **Your Points :** `{points}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 **AVAILABLE SERVICES**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{service_lines}\n"
        f"🔗 **Your Referral Link :**\n"
        f"`https://t.me/{context.bot.username}?start={uid}`\n\n"
        f"_Earn **+5 Points** for every successful referral!_\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [InlineKeyboardButton("🎁  Redeem Account", callback_data="show_services")],
        [
            InlineKeyboardButton("💰  My Points", callback_data="my_points"),
            InlineKeyboardButton("📦  Stock", callback_data="stock_status"),
        ],
        [
            InlineKeyboardButton("🔗  Referral", callback_data="referral_link"),
            InlineKeyboardButton("🎟  Coupon", callback_data="coupon_menu"),
        ],
        [
            InlineKeyboardButton("👑  Leaderboard", callback_data="leaderboard"),
            InlineKeyboardButton("💳  Buy Points", callback_data="buy_points"),
        ],
        [InlineKeyboardButton("📞  Contact Admin", url=f"https://t.me/{md(context.bot.username)}")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    try:
        photos = await context.bot.get_user_profile_photos(uid, limit=1)
        if photos.total_count > 0:
            fid = photos.photos[0][-1].file_id
            return await update.message.reply_photo(photo=fid, caption=text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
    except:
        pass

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid  = user.id

    banned = users_col.find_one({"user_id": uid, "banned": True})
    if banned:
        return await update.message.reply_text("🚫 **You have been banned from using this bot.**", parse_mode=ParseMode.MARKDOWN)

    if context.args:
        try:
            context.user_data["ref"] = int(context.args[0])
        except:
            pass

    joined = await check_join(context.bot, uid)
    if not joined:
        keyboard = [[InlineKeyboardButton(f"📢  Join {ch}", url=f"https://t.me/{ch.replace('@','')}")] for ch in CHANNELS]
        keyboard.append([InlineKeyboardButton("✅  I've Joined — Verify", callback_data="verify_join")])
        return await update.message.reply_text(
            "╔══════════════════════╗\n"
            "     ⚠️  **ACCESS REQUIRED**\n"
            "╚══════════════════════╝\n\n"
            "**You must join all our channels to use this bot.**\n\n"
            "👇 **Join the channels below, then click Verify.**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    ref = context.user_data.pop("ref", None)
    existing = users_col.find_one({"user_id": uid})

    if not existing:
        users_col.insert_one({
            "user_id":  uid,
            "username": user.username,
            "name":     user.first_name,
            "points":   5,
            "joined":   datetime.now(),
            "banned":   False
        })

        if ref and ref != uid:
            ref_user = users_col.find_one({"user_id": ref})
            if ref_user:
                await add_points(ref, 5)
                total = await get_points(ref)
                try:
                    await context.bot.send_message(ref,
                        f"🎉 **REFERRAL BONUS!**\n\n"
                        f"👤 **New User :** {md(user.first_name)}\n"
                        f"💰 **+5 Points Added**\n"
                        f"💎 **Total Points :** `{total}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass

        await log(context.bot,
            f"🔥 **NEW USER JOINED**\n\n"
            f"👤 **Name :** {md(user.first_name)}\n"
            f"🆔 **ID :** `{uid}`\n"
            f"📛 **Username :** @{md(user.username or 'N/A')}\n"
            f"🎁 **Welcome Bonus :** +5 Points"
        )

    await send_start(update, context, user)

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    data   = query.data
    uid    = query.from_user.id
    user   = query.from_user

    banned = users_col.find_one({"user_id": uid, "banned": True})
    if banned:
        return await query.answer("🚫 You are banned.", show_alert=True)

    if data == "verify_join":
        joined = await check_join(context.bot, uid)
        if joined:
            await query.edit_message_text(
                "✅ **Verified Successfully!**\n\nSend /start to open your dashboard.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.answer("❌ You haven't joined all channels yet!", show_alert=True)

    elif data == "my_points":
        pts = await get_points(uid)
        await query.message.reply_text(
            f"💰 **YOUR POINTS BALANCE**\n\n"
            f"👤 **User :** {md(user.first_name)}\n"
            f"💎 **Points :** `{pts}`",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "stock_status":
        services = list(services_col.find({}))
        if not services:
            return await query.message.reply_text("📦 **No services available yet.**", parse_mode=ParseMode.MARKDOWN)
        text = "📦 **CURRENT STOCK STATUS**\n\n"
        for s in services:
            cnt = stocks_col.count_documents({"service": s["name"], "redeemed": False})
            text += f"  ┣ **{s['name']}** ─ {cnt} accounts available\n"
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    elif data == "referral_link":
        await query.message.reply_text(
            f"🔗 **YOUR REFERRAL LINK**\n\n"
            f"`https://t.me/{context.bot.username}?start={uid}`\n\n"
            f"💰 **+5 Points** credited for every successful referral!",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "coupon_menu":
        await query.message.reply_text(
            "🎟 **REDEEM A COUPON**\n\n"
            "**Usage :** `/redeem YOUR_COUPON_CODE`\n\n"
            "_Enter your coupon code after the command._",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "buy_points":
        services = list(services_col.find({}))
        text = "💳 **BUY POINTS / SUBSCRIPTIONS**\n\n"
        for s in services:
            inr = s.get("inr_price", "N/A")
            pts = s.get("points_cost", "N/A")
            text += f"  ┣ **{s['name']}** ─ ₹{inr} = {pts} Points\n"
        text += "\n📞 **Contact Admin to purchase :** @" + md(context.bot.username)
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    elif data == "leaderboard":
        top  = list(users_col.find({}).sort("points", -1).limit(10))
        text = "👑 **TOP 10 LEADERBOARD**\n\n"
        medals = ["🥇","🥈","🥉"] + ["🏅"]*7
        for i, u in enumerate(top):
            text += f"{medals[i]} **{md(u.get('name','Unknown'))}** ─ `{u.get('points',0)}` pts\n"
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    elif data == "show_services":
        services = list(services_col.find({}))
        if not services:
            return await query.answer("❌ No services available right now.", show_alert=True)
        buttons = []
        for s in services:
            cnt = stocks_col.count_documents({"service": s["name"], "redeemed": False})
            inr = s.get("inr_price","?")
            pts = s.get("points_cost","?")
            buttons.append([InlineKeyboardButton(
                f"{s.get('emoji','📦')}  {s['name']}  ─  {pts} pts  |  ₹{inr}  |  Stock: {cnt}",
                callback_data=f"redeem_service:{s['name']}"
            )])
        buttons.append([InlineKeyboardButton("🔙  Back", callback_data="back_home")])
        await query.edit_message_text(
            "🎁 **SELECT SERVICE TO REDEEM**\n\n_Choose the account you want to redeem below:_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data.startswith("redeem_service:"):
        svc_name = data.split(":", 1)[1]
        svc = services_col.find_one({"name": svc_name})
        if not svc:
            return await query.answer("❌ Service not found.", show_alert=True)

        pts_cost = svc.get("points_cost", 999999)
        pts = await get_points(uid)
        if pts < pts_cost:
            return await query.answer(f"❌ You need {pts_cost} points. You have {pts}.", show_alert=True)

        stock = stocks_col.find_one({"service": svc_name, "redeemed": False})
        if not stock:
            return await query.answer(f"❌ {svc_name} is out of stock!", show_alert=True)

        await remove_points(uid, pts_cost)
        stocks_col.update_one({"_id": stock["_id"]}, {
            "$set": {"redeemed": True, "redeemed_by": uid, "redeemed_at": datetime.now()}
        })

        remaining = await get_points(uid)
        left = stocks_col.count_documents({"service": svc_name, "redeemed": False})

        await query.message.reply_text(
            f"✅ **{svc_name.upper()} ACCOUNT REDEEMED!**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 **Account Details :**\n"
            f"`{stock['account']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Points Spent :** `{pts_cost}`\n"
            f"💎 **Remaining Points :** `{remaining}`\n"
            f"📦 **Stock Left :** `{left}`",
            parse_mode=ParseMode.MARKDOWN
        )

        await log(context.bot,
            f"🎉 **ACCOUNT REDEEMED**\n\n"
            f"👤 **User :** {md(user.first_name)}\n"
            f"🆔 **ID :** `{uid}`\n"
            f"📛 **Username :** @{md(user.username or 'N/A')}\n"
            f"📦 **Service :** **{svc_name}**\n"
            f"💰 **Points Spent :** `{pts_cost}`\n"
            f"⏰ **Time :** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    elif data == "back_home":
        services = list(services_col.find({}))
        pts = await get_points(uid)
        service_lines = ""
        for s in services:
            cnt = stocks_col.count_documents({"service": s["name"], "redeemed": False})
            service_lines += f"  ┣ **{s['name']}** ─ 💰 {s.get('points_cost','?')} pts  ₹{s.get('inr_price','?')}  📦 {cnt}\n"
        if not service_lines:
            service_lines = "  ┗ _No services added yet_\n"

        text = (
            f"╔══════════════════════════╗\n"
            f"       🌟 **PREMIUM REDEEM BOT** 🌟\n"
            f"╚══════════════════════════╝\n\n"
            f"👤 **Name :** {md(user.first_name)}\n"
            f"🆔 **User ID :** `{uid}`\n"
            f"💰 **Your Points :** `{pts}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 **AVAILABLE SERVICES**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{service_lines}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        buttons = [
            [InlineKeyboardButton("🎁  Redeem Account", callback_data="show_services")],
            [InlineKeyboardButton("💰  My Points", callback_data="my_points"), InlineKeyboardButton("📦  Stock", callback_data="stock_status")],
            [InlineKeyboardButton("🔗  Referral", callback_data="referral_link"), InlineKeyboardButton("🎟  Coupon", callback_data="coupon_menu")],
            [InlineKeyboardButton("👑  Leaderboard", callback_data="leaderboard"), InlineKeyboardButton("💳  Buy Points", callback_data="buy_points")],
            [InlineKeyboardButton("📞  Contact Admin", url=f"https://t.me/{context.bot.username}")],
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("admin_remove_service:"):
        if not is_admin(uid): return
        svc_name = data.split(":", 1)[1]
        services_col.delete_one({"name": svc_name})
        await query.answer(f"✅ {svc_name} removed.", show_alert=True)
        await manage_services_menu(query)

    elif data == "admin_services_menu":
        if not is_admin(uid): return
        await manage_services_menu(query)

async def manage_services_menu(query):
    services = list(services_col.find({}))
    text = "⚙️ **MANAGE SERVICES**\n\n_Click a service to remove it, or use /addservice to add new._\n\n"
    buttons = []
    for s in services:
        cnt = stocks_col.count_documents({"service": s["name"], "redeemed": False})
        text += f"  ┣ **{s['name']}** ─ 📦 {cnt} stock  💰 {s.get('points_cost','?')} pts  ₹{s.get('inr_price','?')}\n"
        buttons.append([InlineKeyboardButton(f"🗑  Remove {s['name']}", callback_data=f"admin_remove_service:{s['name']}")])
    if not services:
        text += "  ┗ _No services configured_"
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

async def gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 **Admin only.**", parse_mode=ParseMode.MARKDOWN)

    if len(context.args) != 2:
        return await update.message.reply_text(
            "**Usage :** `/gen <count> <points>`\n\n"
            "**Example :** `/gen 10 1` — generates 10 coupons worth 1 point each\n"
            "`/gen 5 20` — generates 5 coupons worth 20 points each",
            parse_mode=ParseMode.MARKDOWN
        )

    try:
        count  = int(context.args[0])
        points = int(context.args[1])
    except:
        return await update.message.reply_text("❌ **Invalid numbers.**", parse_mode=ParseMode.MARKDOWN)

    if count < 1 or count > 500:
        return await update.message.reply_text("❌ **Count must be between 1 and 500.**", parse_mode=ParseMode.MARKDOWN)

    codes = []
    for _ in range(count):
        code = gen_coupon_code()
        coupons_col.insert_one({
            "code":    code,
            "points":  points,
            "redeemed_by": None,
            "expire":  datetime.now() + timedelta(days=30)
        })
        codes.append(code)

    codes_text = "\n".join([f"`{c}`" for c in codes])

    msg = (
        f"✅ **{count} COUPONS GENERATED**\n\n"
        f"💰 **Points Per Coupon :** `{points}`\n"
        f"⏰ **Valid For :** 30 Days\n"
        f"🔒 **Each code: one-time use only**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**COUPON CODES :**\n\n"
        f"{codes_text}"
    )

    if len(msg) > 4096:
        chunks = []
        chunk = f"✅ **{count} COUPONS GENERATED — {points} pts each**\n\n"
        for code in codes:
            line = f"`{code}`\n"
            if len(chunk) + len(line) > 4090:
                chunks.append(chunk)
                chunk = ""
            chunk += line
        if chunk:
            chunks.append(chunk)
        for ch in chunks:
            await update.message.reply_text(ch, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if len(context.args) != 1:
        return await update.message.reply_text(
            "**Usage :** `/redeem YOUR_COUPON_CODE`",
            parse_mode=ParseMode.MARKDOWN
        )

    code = context.args[0].upper().strip()
    data = coupons_col.find_one({"code": code})

    if not data:
        return await update.message.reply_text("❌ **Invalid coupon code.**", parse_mode=ParseMode.MARKDOWN)

    if datetime.now() > data["expire"]:
        return await update.message.reply_text("❌ **This coupon has expired.**", parse_mode=ParseMode.MARKDOWN)

    if data.get("redeemed_by") is not None:
        return await update.message.reply_text("❌ **This coupon has already been redeemed.**", parse_mode=ParseMode.MARKDOWN)

    await add_points(uid, data["points"])
    coupons_col.update_one({"code": code}, {"$set": {"redeemed_by": uid, "redeemed_at": datetime.now()}})

    total = await get_points(uid)

    await update.message.reply_text(
        f"✅ **COUPON REDEEMED SUCCESSFULLY!**\n\n"
        f"🎟 **Code :** `{code}`\n"
        f"💰 **Points Added :** `+{data['points']}`\n"
        f"💎 **Total Points :** `{total}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def addservice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 **Admin only.**", parse_mode=ParseMode.MARKDOWN)

    if len(context.args) < 3:
        return await update.message.reply_text(
            "**Usage :** `/addservice <Name> <PointsCost> <INRPrice> [emoji]`\n\n"
            "**Example :**\n"
            "`/addservice Netflix 40 30 🎬`\n"
            "`/addservice NordVPN 25 20 🔒`\n"
            "`/addservice AmazonPrime 30 25 📺`",
            parse_mode=ParseMode.MARKDOWN
        )

    try:
        name       = context.args[0]
        pts_cost   = int(context.args[1])
        inr_price  = int(context.args[2])
        emoji      = context.args[3] if len(context.args) > 3 else "📦"
    except:
        return await update.message.reply_text("❌ **Invalid format.**", parse_mode=ParseMode.MARKDOWN)

    existing = services_col.find_one({"name": name})
    if existing:
        services_col.update_one({"name": name}, {"$set": {"points_cost": pts_cost, "inr_price": inr_price, "emoji": emoji}})
        await update.message.reply_text(f"✅ **{name} updated.**\n💰 {pts_cost} pts | ₹{inr_price}", parse_mode=ParseMode.MARKDOWN)
    else:
        services_col.insert_one({"name": name, "points_cost": pts_cost, "inr_price": inr_price, "emoji": emoji})
        await update.message.reply_text(
            f"✅ **SERVICE ADDED**\n\n"
            f"📦 **Name :** {name}\n"
            f"💰 **Points Cost :** {pts_cost}\n"
            f"₹ **INR Price :** {inr_price}\n"
            f"🔖 **Emoji :** {emoji}",
            parse_mode=ParseMode.MARKDOWN
        )

async def removeservice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        services = list(services_col.find({}))
        buttons  = [[InlineKeyboardButton(f"🗑  {s['name']}", callback_data=f"admin_remove_service:{s['name']}")] for s in services]
        return await update.message.reply_text(
            "⚙️ **MANAGE SERVICES**\n\n_Click to remove a service:_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
        )

    name = context.args[0]
    services_col.delete_one({"name": name})
    await update.message.reply_text(f"✅ **{name} removed.**", parse_mode=ParseMode.MARKDOWN)

async def addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("🚫 **Admin only.**", parse_mode=ParseMode.MARKDOWN)

    services = list(services_col.find({}))
    if not services:
        return await update.message.reply_text(
            "❌ **No services found.**\n\nAdd a service first using `/addservice`.",
            parse_mode=ParseMode.MARKDOWN
        )

    if not context.args:
        text = "**Usage :** `/addstock <ServiceName>`\n\n**Available Services :**\n"
        for s in services:
            text += f"  ┣ **{s['name']}**\n"
        return await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    svc_name = context.args[0]
    svc = services_col.find_one({"name": svc_name})
    if not svc:
        return await update.message.reply_text(f"❌ **Service '{svc_name}' not found.**", parse_mode=ParseMode.MARKDOWN)

    context.user_data["addstock_service"] = svc_name
    context.user_data["addstock"] = True

    await update.message.reply_text(
        f"📦 **ADD STOCK FOR {svc_name.upper()}**\n\n"
        f"Send accounts **one per message**.\n"
        f"When done, send: `done`\n\n"
        f"_Format example: `email:password` or any format you prefer_",
        parse_mode=ParseMode.MARKDOWN
    )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    total = users_col.count_documents({})
    banned_cnt = users_col.count_documents({"banned": True})
    services = list(services_col.find({}))
    stock_lines = ""
    for s in services:
        cnt = stocks_col.count_documents({"service": s["name"], "redeemed": False})
        stock_lines += f"  ┣ **{s['name']}** ─ {cnt} accounts\n"

    text = (
        f"╔══════════════════════════╗\n"
        f"       ⚙️ **ADMIN CONTROL PANEL**\n"
        f"╚══════════════════════════╝\n\n"
        f"📊 **STATS**\n"
        f"  ┣ 👥 Total Users : `{total}`\n"
        f"  ┣ 🚫 Banned : `{banned_cnt}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 **STOCK STATUS**\n"
        f"{stock_lines if stock_lines else '  ┗ No services configured'}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 **COMMANDS**\n\n"
        f"**COUPONS**\n"
        f"  ┣ `/gen 10 5` — 10 coupons × 5 pts\n\n"
        f"**SERVICES**\n"
        f"  ┣ `/addservice Netflix 40 30 🎬`\n"
        f"  ┣ `/removeservice Netflix`\n\n"
        f"**STOCK**\n"
        f"  ┣ `/addstock Netflix`\n\n"
        f"**POINTS**\n"
        f"  ┣ `/addpts <userid> <amount>`\n"
        f"  ┣ `/removepts <userid> <amount>`\n\n"
        f"**USERS**\n"
        f"  ┣ `/ban <userid>`\n"
        f"  ┣ `/unban <userid>`\n"
        f"  ┣ `/userinfo <userid>`\n"
        f"  ┣ `/users`\n"
        f"  ┣ `/stats`\n\n"
        f"**BROADCAST**\n"
        f"  ┗ Reply to msg + `/broadcast`"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        return await update.message.reply_text("**Usage :** `/ban <userid>`", parse_mode=ParseMode.MARKDOWN)
    try:
        uid = int(context.args[0])
    except:
        return await update.message.reply_text("❌ **Invalid user ID.**", parse_mode=ParseMode.MARKDOWN)
    users_col.update_one({"user_id": uid}, {"$set": {"banned": True}}, upsert=True)
    await update.message.reply_text(f"✅ **User `{uid}` has been banned.**", parse_mode=ParseMode.MARKDOWN)
    try:
        await context.bot.send_message(uid, "🚫 **You have been banned from this bot.**", parse_mode=ParseMode.MARKDOWN)
    except: pass

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        return await update.message.reply_text("**Usage :** `/unban <userid>`", parse_mode=ParseMode.MARKDOWN)
    try:
        uid = int(context.args[0])
    except:
        return await update.message.reply_text("❌ **Invalid user ID.**", parse_mode=ParseMode.MARKDOWN)
    users_col.update_one({"user_id": uid}, {"$set": {"banned": False}})
    await update.message.reply_text(f"✅ **User `{uid}` has been unbanned.**", parse_mode=ParseMode.MARKDOWN)
    try:
        await context.bot.send_message(uid, "✅ **You have been unbanned. Send /start to continue.**", parse_mode=ParseMode.MARKDOWN)
    except: pass

async def addpts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) != 2:
        return await update.message.reply_text("**Usage :** `/addpts <userid> <amount>`", parse_mode=ParseMode.MARKDOWN)
    try:
        uid = int(context.args[0])
        amt = int(context.args[1])
    except:
        return await update.message.reply_text("❌ **Invalid values.**", parse_mode=ParseMode.MARKDOWN)
    await add_points(uid, amt)
    total = await get_points(uid)
    await update.message.reply_text(
        f"✅ **POINTS ADDED**\n\n"
        f"🆔 **User ID :** `{uid}`\n"
        f"💰 **Added :** `+{amt}`\n"
        f"💎 **Total :** `{total}`",
        parse_mode=ParseMode.MARKDOWN
    )
    try:
        await context.bot.send_message(uid,
            f"🎉 **POINTS RECEIVED!**\n\n"
            f"💰 **+{amt} Points** added to your account by Admin.\n"
            f"💎 **Total Points :** `{total}`",
            parse_mode=ParseMode.MARKDOWN
        )
    except: pass

async def removepts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if len(context.args) != 2:
        return await update.message.reply_text("**Usage :** `/removepts <userid> <amount>`", parse_mode=ParseMode.MARKDOWN)
    try:
        uid = int(context.args[0])
        amt = int(context.args[1])
    except:
        return await update.message.reply_text("❌ **Invalid values.**", parse_mode=ParseMode.MARKDOWN)
    await remove_points(uid, amt)
    total = await get_points(uid)
    await update.message.reply_text(
        f"✅ **POINTS REMOVED**\n\n"
        f"🆔 **User ID :** `{uid}`\n"
        f"💰 **Removed :** `-{amt}`\n"
        f"💎 **Remaining :** `{total}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        return await update.message.reply_text("**Usage :** `/userinfo <userid>`", parse_mode=ParseMode.MARKDOWN)
    try:
        uid = int(context.args[0])
    except:
        return await update.message.reply_text("❌ **Invalid user ID.**", parse_mode=ParseMode.MARKDOWN)
    u = users_col.find_one({"user_id": uid})
    if not u:
        return await update.message.reply_text("❌ **User not found.**", parse_mode=ParseMode.MARKDOWN)
    redeems = stocks_col.count_documents({"redeemed_by": uid})
    joined = u.get("joined", "N/A")
    joined_str = joined.strftime("%Y-%m-%d") if isinstance(joined, datetime) else str(joined)
    await update.message.reply_text(
        f"👤 **USER INFO**\n\n"
        f"🆔 **ID :** `{uid}`\n"
        f"📛 **Name :** {md(u.get('name','N/A'))}\n"
        f"🔖 **Username :** @{md(u.get('username','N/A'))}\n"
        f"💰 **Points :** `{u.get('points',0)}`\n"
        f"🎁 **Redeems :** `{redeems}`\n"
        f"🚫 **Banned :** {'Yes' if u.get('banned') else 'No'}\n"
        f"📅 **Joined :** {joined_str}",
        parse_mode=ParseMode.MARKDOWN
    )

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    total  = users_col.count_documents({})
    banned = users_col.count_documents({"banned": True})
    active = total - banned
    await update.message.reply_text(
        f"👥 **USER STATISTICS**\n\n"
        f"  ┣ **Total :** `{total}`\n"
        f"  ┣ **Active :** `{active}`\n"
        f"  ┗ **Banned :** `{banned}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    total  = users_col.count_documents({})
    coupons= coupons_col.count_documents({})
    used_c = coupons_col.count_documents({"redeemed_by": {"$ne": None}})
    redeems= stocks_col.count_documents({"redeemed": True})
    services = list(services_col.find({}))
    stock_lines = ""
    for s in services:
        cnt = stocks_col.count_documents({"service": s["name"], "redeemed": False})
        stock_lines += f"  ┣ **{s['name']}** ─ `{cnt}` available\n"

    await update.message.reply_text(
        f"📊 **BOT STATISTICS**\n\n"
        f"👥 **Users :** `{total}`\n"
        f"🎟 **Coupons Generated :** `{coupons}`\n"
        f"✅ **Coupons Used :** `{used_c}`\n"
        f"🎁 **Total Redeems :** `{redeems}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 **STOCK STATUS**\n"
        f"{stock_lines if stock_lines else '  ┗ No services'}",
        parse_mode=ParseMode.MARKDOWN
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not update.message.reply_to_message:
        return await update.message.reply_text("**Reply to a message, then use /broadcast**", parse_mode=ParseMode.MARKDOWN)

    all_users = list(users_col.find({"banned": {"$ne": True}}))
    msg = update.message.reply_to_message
    status = await update.message.reply_text(f"📢 **Broadcasting to {len(all_users)} users...**", parse_mode=ParseMode.MARKDOWN)
    sent = failed = 0

    for u in all_users:
        try:
            await msg.copy(u["user_id"])
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1

    await status.edit_text(
        f"✅ **BROADCAST COMPLETE**\n\n"
        f"✔️ **Sent :** `{sent}`\n"
        f"❌ **Failed :** `{failed}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if context.user_data.get("addstock"):
        svc_name = context.user_data.get("addstock_service", "Unknown")
        text = update.message.text.strip()

        if text.lower() == "done":
            context.user_data["addstock"] = False
            context.user_data.pop("addstock_service", None)
            cnt = stocks_col.count_documents({"service": svc_name, "redeemed": False})
            return await update.message.reply_text(
                f"✅ **STOCK SAVED FOR {svc_name.upper()}**\n\n"
                f"📦 **Total Available :** `{cnt}`",
                parse_mode=ParseMode.MARKDOWN
            )

        stocks_col.insert_one({"service": svc_name, "account": text, "redeemed": False, "added_at": datetime.now()})
        await update.message.reply_text(f"✅ **Added to {svc_name} stock.**", parse_mode=ParseMode.MARKDOWN)

Thread(target=run_flask).start()

application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start",         start))
application.add_handler(CommandHandler("gen",           gen))
application.add_handler(CommandHandler("redeem",        redeem))
application.add_handler(CommandHandler("addstock",      addstock))
application.add_handler(CommandHandler("addservice",    addservice))
application.add_handler(CommandHandler("removeservice", removeservice))
application.add_handler(CommandHandler("admin",         admin_cmd))
application.add_handler(CommandHandler("ban",           ban))
application.add_handler(CommandHandler("unban",         unban))
application.add_handler(CommandHandler("addpts",        addpts))
application.add_handler(CommandHandler("removepts",     removepts))
application.add_handler(CommandHandler("userinfo",      userinfo))
application.add_handler(CommandHandler("users",         users_cmd))
application.add_handler(CommandHandler("stats",         stats_cmd))
application.add_handler(CommandHandler("broadcast",     broadcast))
application.add_handler(CallbackQueryHandler(callbacks))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

print("✅ BOT STARTED SUCCESSFULLY")

application.run_polling(drop_pending_updates=True)
