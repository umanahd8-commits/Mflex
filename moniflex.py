import telebot
from telebot import types
import time
import datetime
import random
import os
import psycopg2

# ---------- CONFIG ----------
BOT_TOKEN = "8478769265:AAFk0HRmbbNwulr1DEu7-QYojsQ4yBv3kaA"
ADMIN_IDS = [7753547171, 8303629661]
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

# ---------- DB HELPERS (POSTGRESQL VERSION) ----------
def get_db_connection():
    """Get PostgreSQL connection for Railway"""
    try:
        DATABASE_URL = os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except:
        # Fallback to SQLite if PostgreSQL fails
        import sqlite3
        return sqlite3.connect("earning_bot.db")

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
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
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        amount INTEGER,
        status TEXT,
        receipt_file_id TEXT,
        created_at INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        amount INTEGER,
        status TEXT,
        account_details TEXT,
        admin_receipt_file_id TEXT,
        created_at INTEGER,
        processed_at INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS referrals (
        id SERIAL PRIMARY KEY,
        referrer_id BIGINT,
        referred_id BIGINT,
        deposit_id INTEGER,
        bonus_amount INTEGER,
        created_at INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS pending_actions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT UNIQUE,
        action TEXT,
        data TEXT,
        created_at INTEGER
    )""")
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Convert SQLite ? to PostgreSQL %s
    if "?" in query:
        query = query.replace("?", "%s")
        
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
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO deposits (user_id, amount, status, receipt_file_id, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, None, "awaiting_amount", receipt_file_id, now_ts())
    )
    deposit_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return deposit_id

def finalize_deposit_amount(deposit_id, amount):
    db_execute("UPDATE deposits SET amount = %s, status = %s WHERE id = %s", (amount, "pending", deposit_id), commit=True)

def insert_withdrawal(user_id, amount, account_details):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO withdrawals (user_id, amount, status, account_details, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, amount, "pending", account_details, now_ts())
    )
    withdraw_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return withdraw_id

def create_pending_action(user_id, action, data=""):
    db_execute("DELETE FROM pending_actions WHERE user_id = %s", (user_id,), commit=True)
    db_execute("INSERT INTO pending_actions (user_id, action, data, created_at) VALUES (%s, %s, %s, %s)",
               (user_id, action, str(data), now_ts()), commit=True)

def get_pending_action(user_id):
    return db_execute("SELECT id, user_id, action, data FROM pending_actions WHERE user_id = %s", (user_id,), fetchone=True)

def clear_pending_action(user_id):
    db_execute("DELETE FROM pending_actions WHERE user_id = %s", (user_id,), commit=True)

# ---------- UTILS (EXACTLY THE SAME) ----------
def now_ts():
    return int(time.time())

def ensure_user(user):
    u = db_execute("SELECT user_id FROM users WHERE user_id = %s", (user.id,), fetchone=True)
    if not u:
        db_execute(
            "INSERT INTO users (user_id, username, first_name, joined_at) VALUES (%s, %s, %s, %s)",
            (user.id, user.username or "", user.first_name or "", now_ts()),
            commit=True
        )

def get_user_row(user_id):
    return db_execute("SELECT * FROM users WHERE user_id = %s", (user_id,), fetchone=True)

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

# ---------- MARKUPS (EXACTLY THE SAME) ----------
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

# ---------- HANDLERS (EXACTLY THE SAME AS YOUR ORIGINAL) ----------
@bot.message_handler(commands=['start'])
def handle_start(m: types.Message):
    ensure_user(m.from_user)
    args = m.text.split()
    if len(args) > 1:
        try:
            referrer = int(args[1])
            if referrer != m.from_user.id:
                db_execute("UPDATE users SET referrer_id = %s WHERE user_id = %s AND referrer_id IS NULL", (referrer, m.from_user.id), commit=True)
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

# ADMIN COMMANDS (EXACTLY THE SAME)
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
        db_execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amt, uid), commit=True)
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
        db_execute("UPDATE users SET is_registered = 0 WHERE user_id = %s", (uid,), commit=True)
        bot.send_message(m.chat.id, f"✅ User {uid} has been blocked/unregistered.")
        try:
            bot.send_message(uid, "❌ Your account has been blocked by admin. Contact support for details.")
        except:
            pass
    except:
        bot.send_message(m.chat.id, "❌ Invalid user ID.")

# REGULAR MESSAGE HANDLERS (EXACTLY THE SAME)
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
    
    pending_deposit = db_execute("SELECT id, status FROM deposits WHERE user_id = %s AND status IN ('awaiting_amount', 'pending')", (m.from_user.id,), fetchone=True)
    
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
    pending_deposit = db_execute("SELECT id, status FROM deposits WHERE user_id = %s AND status IN ('awaiting_amount', 'pending')", (m.from_user.id,), fetchone=True)
    
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
    deposit = db_execute("SELECT id, user_id, amount, status, receipt_file_id, created_at FROM deposits WHERE id = %s", (deposit_id,), fetchone=True)
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
            pass

# ---------- START BOT (WITH ERROR HANDLING) ----------
if __name__ == "__main__":
    print("🤖 Starting MoniFlex Bot...")
    try:
        init_db()
        print("✅ Database initialized!")
    except Exception as e:
        print(f"⚠️ Database warning: {e}")
    
    # Start bot polling with error recovery
    while True:
        try:
            print("🔄 Starting bot polling...")
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"❌ Bot error: {e}")
            print("🔄 Restarting in 10 seconds...")
            time.sleep(10)