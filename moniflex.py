import telebot
from telebot import types
import sqlite3
import time
import datetime
import random
import os
import psycopg2

# ---------- CONFIG ----------
BOT_TOKEN = "8478769265:AAHEXljntFvm3Wxw7uO3-Bgt7ZOJtc_fkSM"
ADMIN_IDS = [7753547171, 8303629661]
DB_PATH = "earning_bot.db"
JOIN_FEE = 2000
REFERRAL_BONUS = 1000
VIP_UPGRADE_COST = 5000
VIP_REFERRAL_BONUS = 1300
MIN_WITHDRAW = 4000
SPIN_OUTCOMES = [
    ("100", 0.50),
    ("200", 0.30),
    ("500", 0.05),
    ("TRY_AGAIN", 0.15),
]

BANK_ACCOUNT_INFO = (
    "💳 Account Details:\n"
    "Account number: 6141995408\n"
    "Account name: Dorathy Anselem Hanson\n"
    "Bank: Opay"
)

UPDATES_CHANNEL_URL = "https://t.me/moniflex1"
HELP_SUPPORT_URL = "https://t.me/MONIFLEXBOT1"

bot = telebot.TeleBot(BOT_TOKEN)

# ---------- DB HELPERS ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance INTEGER DEFAULT 0,
        is_registered INTEGER DEFAULT 0,
        joined_at INTEGER,
        referrer_id INTEGER,
        is_vip INTEGER DEFAULT 0,
        vip_since INTEGER,
        spins_used INTEGER DEFAULT 0,
        spin_week_start INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        status TEXT,
        receipt_file_id TEXT,
        created_at INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        status TEXT,
        account_details TEXT,
        admin_receipt_file_id TEXT,
        created_at INTEGER,
        processed_at INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        deposit_id INTEGER,
        bonus_amount INTEGER,
        created_at INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS pending_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        action TEXT,
        data TEXT,
        created_at INTEGER
    )""")
    conn.commit()
    conn.close()
    migrate_db()

def migrate_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("SELECT account_details FROM withdrawals LIMIT 1")
        print("Withdrawals table already has the new columns!")
    except sqlite3.OperationalError:
        print("Migrating withdrawals table to add new columns...")
        cur.execute("CREATE TABLE IF NOT EXISTS withdrawals_backup AS SELECT * FROM withdrawals")
        cur.execute("DROP TABLE IF EXISTS withdrawals")
        cur.execute("""CREATE TABLE withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            status TEXT,
            account_details TEXT,
            admin_receipt_file_id TEXT,
            created_at INTEGER,
            processed_at INTEGER
        )""")
        cur.execute("INSERT INTO withdrawals (id, user_id, amount, status, created_at) SELECT id, user_id, amount, status, created_at FROM withdrawals_backup")
        cur.execute("DROP TABLE withdrawals_backup")
        conn.commit()
        print("Withdrawals table migrated successfully!")
    conn.close()

def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    result = None
    if fetchone:
        result = cur.fetchone()
    if fetchall:
        result = cur.fetchall()
    if commit:
        conn.commit()
    conn.close()
    return result

def insert_deposit(user_id, receipt_file_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO deposits (user_id, amount, status, receipt_file_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, None, "awaiting_amount", receipt_file_id, now_ts())
    )
    deposit_id = cur.lastrowid
    conn.commit()
    conn.close()
    return deposit_id

def finalize_deposit_amount(deposit_id, amount):
    db_execute("UPDATE deposits SET amount = ?, status = ? WHERE id = ?", (amount, "pending", deposit_id), commit=True)

def insert_withdrawal(user_id, amount, account_details):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO withdrawals (user_id, amount, status, account_details, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, "pending", account_details, now_ts())
    )
    withdraw_id = cur.lastrowid
    conn.commit()
    conn.close()
    return withdraw_id

def create_pending_action(user_id, action, data=""):
    db_execute("DELETE FROM pending_actions WHERE user_id = ?", (user_id,), commit=True)
    db_execute("INSERT INTO pending_actions (user_id, action, data, created_at) VALUES (?, ?, ?, ?)",
               (user_id, action, str(data), now_ts()), commit=True)

def get_pending_action(user_id):
    return db_execute("SELECT id, user_id, action, data FROM pending_actions WHERE user_id = ?", (user_id,), fetchone=True)

def clear_pending_action(user_id):
    db_execute("DELETE FROM pending_actions WHERE user_id = ?", (user_id,), commit=True)

# ---------- UTILS ----------
def now_ts():
    return int(time.time())

def ensure_user(user):
    u = db_execute("SELECT user_id FROM users WHERE user_id = ?", (user.id,), fetchone=True)
    if not u:
        db_execute(
            "INSERT INTO users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
            (user.id, user.username or "", user.first_name or "", now_ts()),
            commit=True
        )

def get_user_row(user_id):
    return db_execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)

def user_is_admin(user_id):
    return user_id in ADMIN_IDS

def send_to_all_admins(text=None, **kwargs):
    for aid in ADMIN_IDS:
        try:
            if kwargs.get("photo"):
                bot.send_photo(aid, kwargs["photo"], caption=text, reply_markup=kwargs.get("reply_markup"))
            elif kwargs.get("document"):
                bot.send_document(aid, kwargs["document"], caption=text, reply_markup=kwargs.get("reply_markup"))
            else:
                bot.send_message(aid, text, parse_mode=kwargs.get("parse_mode"), reply_markup=kwargs.get("reply_markup"))
        except Exception:
            pass

# ---------- MARKUPS ----------
def main_menu_markup_for(user_id):
    user = get_user_row(user_id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if user and user[4] == 1:
        markup.row("💰 My Balance", "👥 Refer & Earn")
        markup.row("💳 Deposit / Pay Fee", "🎰 Lucky Spin")
        markup.row("⭐ VIP Upgrade", "🚧 Tasks (Coming Soon)")
        markup.row("💵 Withdraw", "ℹ️ Help / Support")
    else:
        markup.row("💳 Deposit / Pay Fee")
        markup.row("ℹ️ Help / Support")
    return markup

def deposit_approve_buttons(deposit_id, user_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_deposit:{deposit_id}:{user_id}"))
    markup.add(types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_deposit:{deposit_id}:{user_id}"))
    return markup

def withdraw_approve_buttons(withdraw_id, user_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw:{withdraw_id}:{user_id}"))
    markup.add(types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw:{withdraw_id}:{user_id}"))
    markup.add(types.InlineKeyboardButton("📤 Upload Receipt", callback_data=f"upload_withdraw_receipt:{withdraw_id}:{user_id}"))
    return markup

def admin_panel_markup():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("👥 Members", callback_data="admin_members"),
        types.InlineKeyboardButton("📥 Deposits", callback_data="admin_deposits"),
        types.InlineKeyboardButton("💸 Withdrawals", callback_data="admin_withdrawals")
    )
    markup.add(
        types.InlineKeyboardButton("🔁 Referrals", callback_data="admin_referrals"),
        types.InlineKeyboardButton("➕ Add Balance (cmd)", callback_data="admin_add_balance_help"),
        types.InlineKeyboardButton("🚫 Block User (cmd)", callback_data="admin_block_help")
    )
    return markup

# ---------- HANDLERS ----------
@bot.message_handler(commands=['start'])
def handle_start(m: types.Message):
    ensure_user(m.from_user)
    args = m.text.split()
    if len(args) > 1:
        try:
            referrer = int(args[1])
            if referrer != m.from_user.id:
                db_execute("UPDATE users SET referrer_id = ? WHERE user_id = ? AND referrer_id IS NULL", (referrer, m.from_user.id), commit=True)
        except:
            pass

    user_row = get_user_row(m.from_user.id)
    welcome_txt = (
        f"👋 Welcome, {m.from_user.first_name}!\n\n"
        f"To start using this bot you MUST pay a registration fee of ₦{JOIN_FEE:,}.\n\n"
        "👉 How to pay:\n"
        f"{BANK_ACCOUNT_INFO}\n\n"
        "After payment, upload your payment receipt using the 'Deposit / Pay Fee' button. Admin will verify & approve.\n\n"
        "If someone referred you, they will receive a referral bonus once your payment is approved.\n\n"
        "Have questions? Tap Help / Support."
    )
    inline = types.InlineKeyboardMarkup()
    inline.add(types.InlineKeyboardButton("🔔 Join Updates Channel", url=UPDATES_CHANNEL_URL))
    inline.add(types.InlineKeyboardButton("📩 Help & Support", url=HELP_SUPPORT_URL))
    
    if user_row and user_row[4] == 0:
        bot.send_message(m.chat.id, welcome_txt, reply_markup=main_menu_markup_for(m.from_user.id))
        bot.send_message(m.chat.id, "Join our updates or contact support:", reply_markup=inline)
    else:
        bot.send_message(m.chat.id, "Welcome back! Use the menu below.", reply_markup=main_menu_markup_for(m.from_user.id))
        bot.send_message(m.chat.id, "Join our updates or contact support:", reply_markup=inline)

@bot.message_handler(commands=['help', 'start_help'])
def help_cmd(m):
    ensure_user(m.from_user)
    txt = (
        "ℹ️ *How this bot works*\n\n"
        f"• Registration fee: ₦{JOIN_FEE:,} (required to unlock earning features).\n"
        f"• Referral bonus: ₦{REFERRAL_BONUS:,} for each friend who pays. VIPs earn ₦{VIP_REFERRAL_BONUS:,} per referral.\n"
        f"• Minimum withdrawal: ₦{MIN_WITHDRAW:,}.\n\n"
        "Steps to start:\n1) Tap *Deposit / Pay Fee* and upload your payment receipt.\n2) Confirm the amount when asked.\n3) Admin will verify & approve your deposit.\n\n"
        "After approval you'll be able to use referrals, purchase VIP, spin, and request withdrawals.\n\n"
        "Admins: use /adminpanel to manage members, deposits and withdrawals."
    )
    inline = types.InlineKeyboardMarkup()
    inline.add(types.InlineKeyboardButton("📩 Contact Support", url=HELP_SUPPORT_URL))
    bot.send_message(m.chat.id, txt, parse_mode="Markdown", reply_markup=inline)

# ADMIN COMMANDS
@bot.message_handler(commands=['adminpanel'])
def admin_panel(m):
    if not user_is_admin(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Unauthorized. You are not an admin.")
        return
    bot.send_message(m.chat.id, "🛠 *Admin Panel* - Select an option below:", 
                    parse_mode="Markdown", reply_markup=admin_panel_markup())

@bot.message_handler(commands=['debug_admin'])
def debug_admin(m):
    user_id = m.from_user.id
    is_admin = user_is_admin(user_id)
    bot.send_message(m.chat.id, 
                    f"🔍 *Debug Info*\n\n"
                    f"👤 Your User ID: `{user_id}`\n"
                    f"🛠 Admin Status: `{is_admin}`\n"
                    f"📋 Configured Admins: `{ADMIN_IDS}`",
                    parse_mode="Markdown")

@bot.message_handler(commands=['admin_add_balance'])
def admin_add_balance(m):
    if not user_is_admin(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Unauthorized.")
        return
    parts = m.text.split()
    if len(parts) != 3:
        bot.send_message(m.chat.id, "Usage: /admin_add_balance <user_id> <amount>")
        return
    try:
        uid = int(parts[1])
        amt = int(parts[2])
        db_execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, uid), commit=True)
        bot.send_message(m.chat.id, f"✅ Added ₦{amt:,} to user {uid}.")
        try:
            bot.send_message(uid, f"💰 Admin added ₦{amt:,} to your account.")
        except:
            pass
    except Exception:
        bot.send_message(m.chat.id, "❌ Invalid input. Usage: /admin_add_balance <user_id> <amount>")

@bot.message_handler(commands=['admin_block'])
def admin_block(m):
    if not user_is_admin(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Unauthorized.")
        return
    parts = m.text.split()
    if len(parts) != 2:
        bot.send_message(m.chat.id, "Usage: /admin_block <user_id>")
        return
    try:
        uid = int(parts[1])
        db_execute("UPDATE users SET is_registered = 0 WHERE user_id = ?", (uid,), commit=True)
        bot.send_message(m.chat.id, f"✅ User {uid} has been blocked/unregistered.")
        try:
            bot.send_message(uid, "❌ Your account has been blocked by admin. Contact support for details.")
        except:
            pass
    except:
        bot.send_message(m.chat.id, "❌ Invalid user ID.")

# REGULAR MESSAGE HANDLERS
@bot.message_handler(regexp=r"^ℹ️ Help / Support$")
def help_support_button(m):
    ensure_user(m.from_user)
    txt = (
        "📞 Help & Support\n\n"
        "Need assistance? Tap the button below to contact our support bot."
    )
    inline = types.InlineKeyboardMarkup()
    inline.add(types.InlineKeyboardButton("💬 Contact Support", url=HELP_SUPPORT_URL))
    bot.send_message(m.chat.id, txt, reply_markup=inline)

@bot.message_handler(regexp="^💰 My Balance$")
def my_balance(m):
    ensure_user(m.from_user)
    user = get_user_row(m.from_user.id)
    if not user or user[4] == 0:
        bot.send_message(m.chat.id, "You must pay and have your deposit approved by admin before accessing account features. Use 'Deposit / Pay Fee'.", reply_markup=main_menu_markup_for(m.from_user.id))
        return
    balance = user[3]
    vip = user[7]
    txt = f"💳 *Your Account*\n\nBalance: ₦{balance:,}\nVIP: {'Yes' if vip else 'No'}\nRegistered: Yes"
    bot.send_message(m.chat.id, txt, parse_mode="Markdown", reply_markup=main_menu_markup_for(m.from_user.id))

@bot.message_handler(regexp="^👥 Refer & Earn$")
def refer_and_earn(m):
    ensure_user(m.from_user)
    user = get_user_row(m.from_user.id)
    if not user or user[4] == 0:
        bot.send_message(m.chat.id, "You must complete registration (pay and be approved) to access referral features. Use 'Deposit / Pay Fee'.", reply_markup=main_menu_markup_for(m.from_user.id))
        return
    invite_link = f"https://t.me/{bot.get_me().username}?start={m.from_user.id}"
    txt = (
        "🤝 *Refer & Earn*\n\n"
        f"Invite friends using your referral link. When they pay the registration fee and admin approves, you get ₦{REFERRAL_BONUS:,} (₦{VIP_REFERRAL_BONUS:,} if you are VIP).\n\n"
        f"Your invite link:\n{invite_link}\n\n"
        "Share it and earn!"
    )
    bot.send_message(m.chat.id, txt, parse_mode="Markdown")

@bot.message_handler(regexp="^💳 Deposit / Pay Fee$")
def deposit_start(m):
    ensure_user(m.from_user)
    user = get_user_row(m.from_user.id)
    
    pending_deposit = db_execute("SELECT id, status FROM deposits WHERE user_id = ? AND status IN ('awaiting_amount', 'pending')", (m.from_user.id,), fetchone=True)
    
    if pending_deposit:
        bot.send_message(m.chat.id, "📋 You already have a deposit request pending approval. Please wait for admin to process your current request before submitting a new one.", reply_markup=main_menu_markup_for(m.from_user.id))
        return
    
    if user and user[4] == 1:
        txt = (
            "You are already registered. If you want to add more balance, upload a deposit receipt here.\n\n"
            f"To pay the join fee: transfer ₦{JOIN_FEE:,} to the account above and upload receipt. After you upload the receipt, admin will verify and approve."
        )
    else:
        txt = (
            "🔔 *To register you must pay ₦2,000.*\n\n"
            f"{BANK_ACCOUNT_INFO}\n\n"
            "Please transfer and then upload your payment receipt in this chat (photo or document). I'll ask you to enter the amount you paid and then forward the receipt to admins for approval."
        )
    
    # Set pending action to indicate user is in deposit flow
    create_pending_action(m.from_user.id, "awaiting_deposit_receipt", "")
    bot.send_message(m.chat.id, txt, parse_mode="Markdown", reply_markup=main_menu_markup_for(m.from_user.id))

# FIXED: Receipt handler - only accepts receipts when user is in deposit flow
@bot.message_handler(content_types=['photo', 'document'], func=lambda m: get_pending_action(m.from_user.id) and get_pending_action(m.from_user.id)[2] == "awaiting_deposit_receipt")
def handle_deposit_receipt(m):
    ensure_user(m.from_user)
    
    # Check if user already has a pending deposit
    pending_deposit = db_execute("SELECT id, status FROM deposits WHERE user_id = ? AND status IN ('awaiting_amount', 'pending')", (m.from_user.id,), fetchone=True)
    
    if pending_deposit:
        bot.reply_to(m, "❌ You already have a deposit request pending approval. Please wait for admin to process your current request.")
        clear_pending_action(m.from_user.id)
        return
    
    # Get file ID
    file_id = None
    content_type = m.content_type
    if content_type == 'photo':
        file_id = m.photo[-1].file_id
    elif content_type == 'document':
        file_id = m.document.file_id
    else:
        bot.reply_to(m, "Please send a photo or document as the receipt.")
        return

    deposit_id = insert_deposit(m.from_user.id, file_id)
    create_pending_action(m.from_user.id, "awaiting_deposit_amount", deposit_id)

    # Ask user to confirm amount
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"₦{JOIN_FEE:,}", callback_data=f"set_deposit_amount:{deposit_id}:{JOIN_FEE}"))
    markup.add(types.InlineKeyboardButton("Other amount", callback_data=f"set_deposit_amount:{deposit_id}:other"))
    markup.add(types.InlineKeyboardButton("Cancel", callback_data=f"cancel_deposit:{deposit_id}"))

    bot.reply_to(m, "✅ Receipt received. Please confirm the amount you paid (tap a quick amount or choose Other to type it).", reply_markup=markup)

def forward_deposit_to_admin(deposit_id):
    deposit = db_execute("SELECT id, user_id, amount, status, receipt_file_id, created_at FROM deposits WHERE id = ?", (deposit_id,), fetchone=True)
    if not deposit:
        return
    uid = deposit[1]
    amount = deposit[2] or JOIN_FEE
    status = deposit[3]
    file_id = deposit[4]
    created = datetime.datetime.fromtimestamp(deposit[5]).strftime("%Y-%m-%d %H:%M")
    caption = (
        f"📥 New deposit (pending verification)\n\n"
        f"Deposit ID: {deposit_id}\nUser ID: {uid}\nAmount: ₦{amount:,}\nStatus: {status}\nUploaded At: {created}\n\n"
        "Approve or Reject using the buttons below."
    )
    # Forward to all admins
    for aid in ADMIN_IDS:
        try:
            try:
                bot.send_photo(aid, file_id, caption=caption, reply_markup=deposit_approve_buttons(deposit_id, uid))
            except Exception:
                bot.send_document(aid, file_id, caption=caption, reply_markup=deposit_approve_buttons(deposit_id, uid))
        except Exception:
            try:
                bot.send_message(aid, caption, reply_markup=deposit_approve_buttons(deposit_id, uid))
            except:
                pass

@bot.message_handler(regexp="^⭐ VIP Upgrade$")
def vip_upgrade(m):
    ensure_user(m.from_user)
    user = get_user_row(m.from_user.id)
    if not user or user[4] == 0:
        bot.send_message(m.chat.id, "You must complete registration and be approved by admin to upgrade to VIP.", reply_markup=main_menu_markup_for(m.from_user.id))
        return
    if user[7] == 1:
        bot.send_message(m.chat.id, "You are already VIP! Enjoy the bonuses and priority withdrawals.", reply_markup=main_menu_markup_for(m.from_user.id))
        return
    txt = (
        f"⭐ *VIP Upgrade — ₦{VIP_UPGRADE_COST:,}*\n\n"
        "Upgrade to VIP to earn ₦1,300 per referral, get priority withdrawals, 2 lucky spins per week, VIP badge and exclusive bonuses.\n\n"
        "You can pay from your balance. Press the button below to purchase VIP (balance will be deducted)."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"Buy VIP for ₦{VIP_UPGRADE_COST:,}", callback_data="buy_vip"))
    bot.send_message(m.chat.id, txt, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(regexp="^🎰 Lucky Spin$")
def lucky_spin_menu(m):
    ensure_user(m.from_user)
    user = get_user_row(m.from_user.id)
    if not user or user[4] == 0:
        bot.send_message(m.chat.id, "You must complete registration (pay and be approved) to use Lucky Spin.", reply_markup=main_menu_markup_for(m.from_user.id))
        return
    spins_allowed = 2 if user[7] == 1 else 1
    week_start = user[10] or 0
    if week_start == 0:
        week_start = now_ts()
        db_execute("UPDATE users SET spin_week_start = ? WHERE user_id = ?", (week_start, m.from_user.id), commit=True)
    if now_ts() - week_start >= 7*24*3600:
        db_execute("UPDATE users SET spin_week_start = ?, spins_used = 0 WHERE user_id = ?", (now_ts(), m.from_user.id), commit=True)
        user = get_user_row(m.from_user.id)

    spins_used = user[9] or 0
    spins_left = max(0, spins_allowed - spins_used)
    txt = (
        f"🎰 Lucky Spin\n\nSpins this week: {spins_left}/{spins_allowed}\n\n"
        "Spin rewards:\n• ₦100\n• ₦200\n• ₦500 (very rare)\n• Try Again\n\nYou can also buy extra spins for ₦100 each (deducted from your balance).\n\nPress Spin to try your luck!"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎯 Spin", callback_data="spin_now"))
    markup.add(types.InlineKeyboardButton("➕ Buy extra spin (₦100)", callback_data="buy_spin"))
    bot.send_message(m.chat.id, txt, reply_markup=markup)

@bot.message_handler(regexp="^🚧 Tasks \\(Coming Soon\\)$")
def tasks_coming_soon(m):
    txt = (
        "🚧 Tasks — Coming Soon\n\n"
        "Exciting ways to earn more will be released soon! Stay tuned to the updates channel for announcements and new task drops."
    )
    bot.send_message(m.chat.id, txt, reply_markup=main_menu_markup_for(m.from_user.id))

@bot.message_handler(regexp="^💵 Withdraw$")
def withdraw_cmd(m):
    ensure_user(m.from_user)
    user = get_user_row(m.from_user.id)
    if not user or user[4] == 0:
        bot.send_message(m.chat.id, "You must pay the registration fee and be approved by admin before requesting withdrawals.", reply_markup=main_menu_markup_for(m.from_user.id))
        return
    create_pending_action(m.from_user.id, "awaiting_withdraw_amount", "")
    bot.send_message(m.chat.id, f"💸 *Withdraw Request*\n\nMinimum withdrawal amount: ₦{MIN_WITHDRAW:,}\n\nReply with the amount you want to withdraw (numbers only).", parse_mode="Markdown")

# ---------- CALLBACK HANDLERS ----------
@bot.callback_query_handler(func=lambda call: call.data.startswith("set_deposit_amount") or call.data.startswith("cancel_deposit"))
def cb_set_deposit_amount(call: types.CallbackQuery):
    try:
        parts = call.data.split(":")
        cmd = parts[0]
        deposit_id = int(parts[1])
        choice = parts[2].strip()
    except Exception:
        bot.answer_callback_query(call.id, "Invalid action.")
        return

    row = db_execute("SELECT id, user_id, amount, status, receipt_file_id FROM deposits WHERE id = ?", (deposit_id,), fetchone=True)
    if not row:
        bot.answer_callback_query(call.id, "Deposit not found.")
        return

    user_id = row[1]
    if cmd == "cancel_deposit":
        db_execute("UPDATE deposits SET status = ? WHERE id = ?", ("cancelled", deposit_id), commit=True)
        clear_pending_action(user_id)
        bot.send_message(user_id, "Your deposit upload has been cancelled. If you want to try again, upload the receipt again.")
        bot.answer_callback_query(call.id, "Deposit cancelled.")
        return

    if choice == "other":
        bot.answer_callback_query(call.id, "Please type the amount you paid (numbers only).")
        bot.send_message(user_id, "Please reply with the amount you paid (numbers only).")
        return
    else:
        try:
            amount = int(choice.replace(",", "").replace(" ", ""))
        except:
            bot.answer_callback_query(call.id, "Invalid amount.")
            return
        finalize_deposit_amount(deposit_id, amount)
        clear_pending_action(user_id)
        bot.answer_callback_query(call.id, f"Amount ₦{amount:,} recorded and forwarded to admins.")
        bot.send_message(user_id, f"✅ Amount ₦{amount:,} recorded. Your receipt has been sent to admins for verification.")
        forward_deposit_to_admin(deposit_id)
        return

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_deposit") or call.data.startswith("reject_deposit"))
def cb_approve_deposit(call: types.CallbackQuery):
    if not user_is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Unauthorized")
        return
    parts = call.data.split(":")
    action = parts[0]
    deposit_id = int(parts[1])
    user_id = int(parts[2])
    deposit = db_execute("SELECT id, user_id, amount, status FROM deposits WHERE id = ?", (deposit_id,), fetchone=True)
    if not deposit:
        bot.answer_callback_query(call.id, "Deposit not found.")
        return
    current_status = deposit[3]
    if action == "approve_deposit":
        if current_status != "pending":
            bot.answer_callback_query(call.id, "Deposit is not in pending state.")
            return
        db_execute("UPDATE deposits SET status = ? WHERE id = ?", ("approved", deposit_id), commit=True)
        db_execute("UPDATE users SET is_registered = 1 WHERE user_id = ?", (user_id,), commit=True)

        # award referral bonus if applicable
        ref_row = db_execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,), fetchone=True)
        if ref_row and ref_row[0]:
            referrer_id = ref_row[0]
            ref_user = db_execute("SELECT is_vip FROM users WHERE user_id = ?", (referrer_id,), fetchone=True)
            bonus = REFERRAL_BONUS
            if ref_user and ref_user[0] == 1:
                bonus = VIP_REFERRAL_BONUS
            db_execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus, referrer_id), commit=True)
            db_execute("INSERT INTO referrals (referrer_id, referred_id, deposit_id, bonus_amount, created_at) VALUES (?, ?, ?, ?, ?)",
                       (referrer_id, user_id, deposit_id, bonus, now_ts()), commit=True)
            try:
                bot.send_message(referrer_id, f"🎉 You received a referral bonus of ₦{bonus:,} because a referred friend completed registration.")
            except:
                pass

        bot.send_message(user_id, "✅ Your payment has been approved by admin. Your account is now registered — you can now earn using referrals, spins, and request withdrawals.", reply_markup=main_menu_markup_for(user_id))
        bot.answer_callback_query(call.id, "Deposit approved.")
        try:
            bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=None)
        except:
            pass
    elif action == "reject_deposit":
        if current_status not in ("pending", "awaiting_amount"):
            bot.answer_callback_query(call.id, "Deposit is not in a rejectable state.")
            return
        db_execute("UPDATE deposits SET status = ? WHERE id = ?", ("rejected", deposit_id), commit=True)
        clear_pending_action(user_id)
        bot.send_message(user_id, "❌ Your payment receipt was rejected by admin. Please check and upload a valid receipt.")
        bot.answer_callback_query(call.id, "Deposit rejected.")
        try:
            bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=None)
        except:
            pass

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip")
def cb_buy_vip(call: types.CallbackQuery):
    ensure_user(call.from_user)
    user = get_user_row(call.from_user.id)
    if not user or user[4] == 0:
        bot.answer_callback_query(call.id, "You must be registered to buy VIP.")
        bot.send_message(call.from_user.id, "You must complete registration before purchasing VIP. Use 'Deposit / Pay Fee'.")
        return
    balance = user[3]
    if balance < VIP_UPGRADE_COST:
        bot.answer_callback_query(call.id, "Insufficient balance to buy VIP.")
        bot.send_message(call.from_user.id, f"Your balance is ₦{balance:,}. You need ₦{VIP_UPGRADE_COST:,} to buy VIP.")
        return
    db_execute("UPDATE users SET balance = balance - ?, is_vip = 1, vip_since = ? WHERE user_id = ?",
               (VIP_UPGRADE_COST, now_ts(), call.from_user.id), commit=True)
    bot.answer_callback_query(call.id, "VIP purchased!")
    bot.send_message(call.from_user.id, "🎉 You are now VIP! Enjoy higher referral earnings and extra spins.", reply_markup=main_menu_markup_for(call.from_user.id))

@bot.callback_query_handler(func=lambda c: c.data in ("spin_now", "buy_spin"))
def cb_spin(call: types.CallbackQuery):
    ensure_user(call.from_user)
    user = get_user_row(call.from_user.id)
    if not user or user[4] == 0:
        bot.answer_callback_query(call.id, "You must complete registration to use spins.")
        bot.send_message(call.from_user.id, "Complete your deposit & approval first.")
        return
    spins_allowed = 2 if user[7] == 1 else 1
    week_start = user[10] or 0
    if week_start == 0 or now_ts() - week_start >= 7*24*3600:
        db_execute("UPDATE users SET spin_week_start = ?, spins_used = 0 WHERE user_id = ?", (now_ts(), call.from_user.id), commit=True)
        user = get_user_row(call.from_user.id)

    spins_used = user[9] or 0
    spins_left = max(0, spins_allowed - spins_used)

    if call.data == "spin_now":
        if spins_left <= 0:
            bot.answer_callback_query(call.id, "No free spins left for this week. Buy extra spin to play more.")
            bot.send_message(call.from_user.id, "No free spins left this week. You can buy extra spins for ₦100 each.")
            return
        db_execute("UPDATE users SET spins_used = spins_used + 1 WHERE user_id = ?", (call.from_user.id,), commit=True)
        r = random.random()
        cumulative = 0.0
        outcome = "TRY_AGAIN"
        for name, prob in SPIN_OUTCOMES:
            cumulative += prob
            if r <= cumulative:
                outcome = name
                break
        if outcome == "TRY_AGAIN":
            bot.send_message(call.from_user.id, "😕 Try Again — no win this time. Better luck next spin!")
        else:
            amount = int(outcome)
            db_execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, call.from_user.id), commit=True)
            bot.send_message(call.from_user.id, f"🎉 You won ₦{amount:,}! It has been added to your balance.")
        bot.answer_callback_query(call.id, "Spin processed.")
    else:  # buy_spin
        if user[3] < 100:
            bot.answer_callback_query(call.id, "Insufficient balance to buy spin. Please deposit or top up your balance.")
            bot.send_message(call.from_user.id, "You need ₦100 to buy a spin. Use Deposit / Pay Fee to upload receipt or ask admin to add balance.")
            return
        db_execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (100, call.from_user.id), commit=True)
        r = random.random()
        cumulative = 0.0
        outcome = "TRY_AGAIN"
        for name, prob in SPIN_OUTCOMES:
            cumulative += prob
            if r <= cumulative:
                outcome = name
                break
        if outcome == "TRY_AGAIN":
            bot.send_message(call.from_user.id, "😕 Try Again — no win this time.")
        else:
            amount = int(outcome)
            db_execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, call.from_user.id), commit=True)
            bot.send_message(call.from_user.id, f"🎉 You won ₦{amount:,}! It has been added to your balance.")
        bot.answer_callback_query(call.id, "Extra spin processed.")

# Withdrawal approval handlers
@bot.callback_query_handler(func=lambda c: c.data.startswith(("approve_withdraw", "reject_withdraw", "upload_withdraw_receipt")))
def cb_withdraw_admin(call: types.CallbackQuery):
    if not user_is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Unauthorized")
        return
    
    try:
        parts = call.data.split(":")
        action = parts[0]
        withdraw_id = int(parts[1])
        user_id = int(parts[2])
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {e}")
        return
    
    wd = db_execute("SELECT id, user_id, amount, status FROM withdrawals WHERE id = ?", (withdraw_id,), fetchone=True)
    if not wd:
        bot.answer_callback_query(call.id, "❌ Withdrawal not found.")
        return
    
    if action == "approve_withdraw":
        bot.answer_callback_query(call.id, "❌ Please upload payment receipt first using 'Upload Receipt' button.")
        
    elif action == "reject_withdraw":
        if wd[3] != "pending":
            bot.answer_callback_query(call.id, "❌ Already processed.")
            return
        
        db_execute("UPDATE withdrawals SET status = ? WHERE id = ?", ("rejected", withdraw_id), commit=True)
        
        try:
            bot.send_message(user_id, f"❌ Your withdrawal request (ID: {withdraw_id}) was rejected by admin.")
        except Exception as e:
            print(f"Could not notify user: {e}")
        
        bot.answer_callback_query(call.id, "✅ Withdrawal rejected.")
        
        try:
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except Exception as e:
            print(f"Could not update message: {e}")
    
    elif action == "upload_withdraw_receipt":
        if wd[3] != "pending":
            bot.answer_callback_query(call.id, "❌ Already processed.")
            return
        
        create_pending_action(call.from_user.id, "admin_upload_withdraw_receipt", str(withdraw_id))
        bot.answer_callback_query(call.id, "📤 Please upload the payment receipt (photo or document).")
        
        bot.send_message(
            call.from_user.id,
            f"📤 *Upload Payment Receipt*\n\n"
            f"Withdrawal ID: `{withdraw_id}`\n"
            f"Please upload the payment receipt (photo or document) for this withdrawal.",
            parse_mode="Markdown"
        )

# Handle admin receipt upload for withdrawals
@bot.message_handler(content_types=['photo', 'document'], func=lambda m: get_pending_action(m.from_user.id) and get_pending_action(m.from_user.id)[2] == "admin_upload_withdraw_receipt")
def handle_admin_withdraw_receipt(m):
    if not user_is_admin(m.from_user.id):
        return
    
    pending = get_pending_action(m.from_user.id)
    if not pending or pending[2] != "admin_upload_withdraw_receipt":
        return
    
    try:
        withdraw_id = int(pending[3])
    except:
        bot.send_message(m.chat.id, "❌ Error processing withdrawal ID.")
        clear_pending_action(m.from_user.id)
        return
    
    file_id = None
    file_type = None
    if m.content_type == 'photo':
        file_id = m.photo[-1].file_id
        file_type = 'photo'
    elif m.content_type == 'document':
        file_id = m.document.file_id
        file_type = 'document'
    
    if not file_id:
        bot.reply_to(m, "❌ Please send a photo or document as the receipt.")
        return
    
    wd = db_execute("SELECT user_id, amount, status FROM withdrawals WHERE id = ?", (withdraw_id,), fetchone=True)
    if not wd:
        bot.send_message(m.chat.id, "❌ Withdrawal not found.")
        clear_pending_action(m.from_user.id)
        return
    
    user_id = wd[0]
    amount = wd[1]
    current_status = wd[2]
    
    if current_status != "pending":
        bot.send_message(m.chat.id, f"❌ Withdrawal already processed (status: {current_status}).")
        clear_pending_action(m.from_user.id)
        return
    
    user_row = get_user_row(user_id)
    if not user_row:
        bot.send_message(m.chat.id, "❌ User not found.")
        clear_pending_action(m.from_user.id)
        return
        
    if user_row[3] < amount:
        bot.send_message(m.chat.id, f"❌ User has insufficient balance (₦{user_row[3]:,} < ₦{amount:,}).")
        clear_pending_action(m.from_user.id)
        return
    
    db_execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id), commit=True)
    db_execute("UPDATE withdrawals SET status = 'completed', admin_receipt_file_id = ?, processed_at = ? WHERE id = ?", 
               (file_id, now_ts(), withdraw_id), commit=True)
    
    try:
        if file_type == 'photo':
            bot.send_photo(
                user_id, 
                file_id, 
                caption=f"📄 *Payment Receipt*\n\nYour withdrawal of ₦{amount:,} has been processed successfully!",
                parse_mode="Markdown"
            )
        else:
            bot.send_document(
                user_id, 
                file_id, 
                caption=f"📄 *Payment Receipt*\n\nYour withdrawal of ₦{amount:,} has been processed successfully!",
                parse_mode="Markdown"
            )
        
        bot.send_message(
            user_id, 
            f"✅ *Withdrawal Completed!*\n\n"
            f"Amount: ₦{amount:,}\n"
            f"Status: Paid\n\n"
            f"Thank you for using our service! 🎉",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Could not notify user: {e}")
        bot.send_message(m.chat.id, f"✅ Receipt uploaded but could not notify user: {e}")
    
    bot.send_message(
        m.chat.id,
        f"✅ *Withdrawal Processed Successfully!*\n\n"
        f"Withdrawal ID: `{withdraw_id}`\n"
        f"User: `{user_id}`\n"
        f"Amount: ₦{amount:,}\n"
        f"Status: Completed ✅",
        parse_mode="Markdown"
    )
    
    clear_pending_action(m.from_user.id)

# ADMIN PANEL CALLBACKS
@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_"))
def admin_callbacks(call: types.CallbackQuery):
    if not user_is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Unauthorized")
        return
    cmd = call.data
    if cmd == "admin_members":
        rows = db_execute("SELECT user_id, username, first_name, balance, is_registered, is_vip FROM users", fetchall=True)
        if not rows:
            bot.send_message(call.from_user.id, "No members found.")
            bot.answer_callback_query(call.id, "No members")
            return
            
        txt = "👥 All Members\n\n"
        for r in rows:
            txt += f"ID: {r[0]} — {r[2]} (@{r[1]}) — ₦{r[3]:,} — Registered: {'Yes' if r[4] else 'No'} — VIP: {'Yes' if r[5] else 'No'}\n"
            
        if len(txt) > 4000:
            parts = [txt[i:i+4000] for i in range(0, len(txt), 4000)]
            for part in parts:
                bot.send_message(call.from_user.id, part)
        else:
            bot.send_message(call.from_user.id, txt)
        bot.answer_callback_query(call.id, "Members listed.")
        
    elif cmd == "admin_deposits":
        rows = db_execute("SELECT id, user_id, amount, status, created_at FROM deposits ORDER BY created_at DESC LIMIT 50", fetchall=True)
        if not rows:
            bot.send_message(call.from_user.id, "No deposits found.")
            bot.answer_callback_query(call.id, "No deposits")
            return
            
        txt = "📥 Deposits (latest 50)\n\n"
        for r in rows:
            created = datetime.datetime.fromtimestamp(r[4]).strftime("%Y-%m-%d %H:%M") if r[4] else "N/A"
            amt = r[2] if r[2] is not None else "(not set)"
            txt += f"ID:{r[0]} User:{r[1]} Amount:{amt} Status:{r[3]} At:{created}\n"
            
        if len(txt) > 4000:
            parts = [txt[i:i+4000] for i in range(0, len(txt), 4000)]
            for part in parts:
                bot.send_message(call.from_user.id, part)
        else:
            bot.send_message(call.from_user.id, txt)
        bot.answer_callback_query(call.id, "Deposits listed.")
        
    elif cmd == "admin_withdrawals":
        rows = db_execute("SELECT id, user_id, amount, status, account_details, created_at FROM withdrawals ORDER BY created_at DESC LIMIT 50", fetchall=True)
        if not rows:
            bot.send_message(call.from_user.id, "No withdrawals found.")
            bot.answer_callback_query(call.id, "No withdrawals")
            return
            
        txt = "💸 Withdrawals (latest 50)\n\n"
        for r in rows:
            created = datetime.datetime.fromtimestamp(r[5]).strftime("%Y-%m-%d %H:%M") if r[5] else "N/A"
            account_preview = r[4][:50] + "..." if r[4] and len(r[4]) > 50 else (r[4] or "No details")
            txt += f"ID:{r[0]} User:{r[1]} Amount:₦{r[2]:,} Status:{r[3]} Account:{account_preview} At:{created}\n"
            
        if len(txt) > 4000:
            parts = [txt[i:i+4000] for i in range(0, len(txt), 4000)]
            for part in parts:
                bot.send_message(call.from_user.id, part)
        else:
            bot.send_message(call.from_user.id, txt)
        bot.answer_callback_query(call.id, "Withdrawals listed.")
        
    elif cmd == "admin_referrals":
        rows = db_execute("SELECT referrer_id, referred_id, bonus_amount, created_at FROM referrals ORDER BY created_at DESC LIMIT 100", fetchall=True)
        if not rows:
            bot.send_message(call.from_user.id, "No referrals found.")
            bot.answer_callback_query(call.id, "No referrals")
            return
            
        txt = "🔁 Referrals (latest 100)\n\n"
        for r in rows:
            created = datetime.datetime.fromtimestamp(r[3]).strftime("%Y-%m-%d %H:%M") if r[3] else "N/A"
            txt += f"Referrer:{r[0]} -> Referred:{r[1]} Bonus:₦{r[2]:,} At:{created}\n"
            
        if len(txt) > 4000:
            parts = [txt[i:i+4000] for i in range(0, len(txt), 4000)]
            for part in parts:
                bot.send_message(call.from_user.id, part)
        else:
            bot.send_message(call.from_user.id, txt)
        bot.answer_callback_query(call.id, "Referrals listed.")
        
    elif cmd == "admin_add_balance_help":
        bot.send_message(call.from_user.id, "To add balance use the command:\n/admin_add_balance <user_id> <amount>\nExample:\n/admin_add_balance 123456789 1000")
        bot.answer_callback_query(call.id, "How-to sent.")
        
    elif cmd == "admin_block_help":
        bot.send_message(call.from_user.id, "To block/unregister a user use the command:\n/admin_block <user_id>\nExample:\n/admin_block 123456789")
        bot.answer_callback_query(call.id, "How-to sent.")
        
    else:
        bot.answer_callback_query(call.id, "Unknown admin command.")

# FALLBACK HANDLER
@bot.message_handler(func=lambda m: True)
def fallback(m):
    ensure_user(m.from_user)
    if m.text and m.text.startswith('/'):
        bot.send_message(m.chat.id, "❌ Unknown command. Use the menu buttons below.", reply_markup=main_menu_markup_for(m.from_user.id))
        return
        
    pending = get_pending_action(m.from_user.id)
    if pending:
        action = pending[2]
        data = pending[3]
        
        if action == "awaiting_deposit_amount":
            if m.text and m.text.strip().isdigit():
                try:
                    amount = int(m.text.strip())
                except:
                    bot.send_message(m.chat.id, "Please send a numeric amount only.")
                    return
                deposit_id = int(data)
                finalize_deposit_amount(deposit_id, amount)
                clear_pending_action(m.from_user.id)
                bot.send_message(m.chat.id, f"✅ Amount ₦{amount:,} recorded. Your receipt has been sent to admins for verification.")
                forward_deposit_to_admin(deposit_id)
                return
            else:
                bot.send_message(m.chat.id, "Please send a numeric amount only.")
                return
                
        elif action == "awaiting_withdraw_amount":
            if m.text and m.text.strip().isdigit():
                try:
                    amount = int(m.text.strip())
                except:
                    bot.send_message(m.chat.id, "Please send a numeric amount only.")
                    return
                    
                user = get_user_row(m.from_user.id)
                if not user or user[4] == 0:
                    bot.send_message(m.chat.id, "You must be registered and approved by admin before requesting withdrawals.")
                    clear_pending_action(m.from_user.id)
                    return
                    
                if amount < MIN_WITHDRAW:
                    bot.send_message(m.chat.id, f"Minimum withdrawal is ₦{MIN_WITHDRAW:,}. Please enter an amount ≥ ₦{MIN_WITHDRAW:,}.")
                    return
                    
                if user[3] < amount:
                    bot.send_message(m.chat.id, f"Insufficient balance. Your balance is ₦{user[3]:,}.")
                    return
                
                create_pending_action(m.from_user.id, "awaiting_account_details", str(amount))
                bot.send_message(m.chat.id, "📝 *Please provide your account details*:\n\nYou can send:\n- Bank name:\n Account number:\n Account name:\n\n\nmake sure your account details are correct to aviod sending funds to wrong account")
                return
            else:
                bot.send_message(m.chat.id, "Please send a numeric amount for withdrawal.")
                return
                
        elif action == "awaiting_account_details":
            try:
                amount = int(data)
            except:
                bot.send_message(m.chat.id, "Error processing withdrawal amount. Please start over.")
                clear_pending_action(m.from_user.id)
                return
            
            account_details = m.text.strip()
            wid = insert_withdrawal(m.from_user.id, amount, account_details)
            clear_pending_action(m.from_user.id)
            
            bot.send_message(m.chat.id, f"✅ Withdrawal request of ₦{amount:,} created and sent to admins for approval (Request ID: {wid}).\n\nYour account details have been recorded.")
            
            txt = (
                f"💸 New Withdrawal Request\n\n"
                f"ID: {wid}\nUser: {m.from_user.first_name} (@{m.from_user.username or 'none'})\nUser ID: {m.from_user.id}\nAmount: ₦{amount:,}\n\n"
                f"Account Details:\n{account_details}\n\n"
                "Approve, reject, or upload receipt using the buttons."
            )
            send_to_all_admins(txt, reply_markup=withdraw_approve_buttons(wid, m.from_user.id))
            return
    
    # Handle random photo/document uploads when not in deposit flow
    if m.content_type in ['photo', 'document']:
        bot.reply_to(m, "❌ I only accept receipts when you're in the deposit process. Please use the '💳 Deposit / Pay Fee' button first to start a deposit request.")
        return
    
    txt = (
        "I didn't understand that. Use the menu below.\n\n"
        "Main commands are available in the buttons.\n"
        "If you paid, upload your payment receipt under Deposit / Pay Fee.\n"
        "For assistance, use Help / Support."
    )
    bot.send_message(m.chat.id, txt, reply_markup=main_menu_markup_for(m.from_user.id))

# ---------- START ----------
if __name__ == "__main__":
    if not BOT_TOKEN or not ADMIN_IDS or len(ADMIN_IDS) < 1:
        print("Please set BOT_TOKEN and ADMIN_IDS in the script before running.")
        exit(1)
    init_db()
    print("Bot is running...")
    bot.infinity_polling()