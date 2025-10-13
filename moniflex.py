import telebot
from telebot import types
import time
import datetime
import random
import os

# Try to import psycopg2, but fallback to sqlite3 if not available
try:
    import psycopg2
    DATABASE_TYPE = "postgres"
except ImportError:
    import sqlite3
    DATABASE_TYPE = "sqlite"
    print("⚠️ psycopg2 not available, using SQLite fallback")

# ---------- CONFIG ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8478769265:AAFk0HRmbbNwulr1DEu7-QYojsQ4yBv3kaA")
ADMIN_IDS = [7753547171, 8303629661]
JOIN_FEE = 2000
REFERRAL_BONUS = 1000
VIP_UPGRADE_COST = 5000
VIP_REFERRAL_BONUS = 1300
MIN_WITHDRAW = 4000

BANK_ACCOUNT_INFO = (
    "💳 Account Details:\n"
    "Account number: 6141995408\n"
    "Account name: Dorathy Anselem Hanson\n"
    "Bank: Opay"
)

UPDATES_CHANNEL_URL = "https://t.me/moniflex1"
HELP_SUPPORT_URL = "https://t.me/MONIFLEXBOT1"

# Initialize bot FIRST
bot = telebot.TeleBot(BOT_TOKEN)

# ---------- SIMPLE DB SETUP (Non-blocking) ----------
def get_db_connection():
    """Get database connection without blocking startup"""
    try:
        if DATABASE_TYPE == "postgres":
            DATABASE_URL = os.environ.get('DATABASE_URL')
            if DATABASE_URL:
                conn = psycopg2.connect(DATABASE_URL, sslmode='require')
                return conn
        # Fallback to SQLite
        import sqlite3
        return sqlite3.connect("/tmp/earning_bot.db")
    except Exception as e:
        print(f"Database connection failed: {e}")
        # Emergency fallback
        import sqlite3
        return sqlite3.connect("/tmp/emergency.db")

def init_db():
    """Initialize database tables without blocking"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create users table
        if DATABASE_TYPE == "postgres":
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
        else:
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
        
        conn.commit()
        conn.close()
        print("✅ Database tables ready!")
    except Exception as e:
        print(f"⚠️ Database init warning: {e}")

def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    """Safe database execution with error handling"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Convert query for PostgreSQL if needed
        if DATABASE_TYPE == "postgres" and "?" in query:
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
    except Exception as e:
        print(f"Database error: {e}")
        return None

# ---------- SIMPLE HANDLERS (Respond immediately) ----------
@bot.message_handler(commands=['start'])
def handle_start(m):
    """Simple start command that works immediately"""
    try:
        user = m.from_user
        welcome_text = f"👋 Welcome {user.first_name}!\n\nI'm MoniFlex Bot! Use the menu below to get started."
        bot.send_message(m.chat.id, welcome_text, reply_markup=main_menu_markup())
    except Exception as e:
        print(f"Start error: {e}")

@bot.message_handler(commands=['help'])
def handle_help(m):
    """Simple help command"""
    help_text = "🆘 Help & Support\n\nNeed assistance? Contact our support team."
    bot.send_message(m.chat.id, help_text)

@bot.message_handler(func=lambda message: True)
def handle_all_messages(m):
    """Catch-all handler to respond to any message"""
    try:
        if m.text == "💰 My Balance":
            bot.send_message(m.chat.id, "💳 Your balance: ₦0\n\nPlease use 'Deposit / Pay Fee' to get started!")
        elif m.text == "💳 Deposit / Pay Fee":
            bot.send_message(m.chat.id, f"📥 Deposit Instructions:\n\n{BANK_ACCOUNT_INFO}\n\nSend ₦{JOIN_FEE:,} and upload your receipt here.")
        elif m.text == "ℹ️ Help / Support":
            bot.send_message(m.chat.id, "📞 Contact support for assistance.")
        else:
            bot.send_message(m.chat.id, "🤖 I'm here! Use the menu buttons below.")
    except Exception as e:
        print(f"Message handling error: {e}")

def main_menu_markup():
    """Simple menu that always works"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 My Balance", "👥 Refer & Earn")
    markup.row("💳 Deposit / Pay Fee", "🎰 Lucky Spin") 
    markup.row("⭐ VIP Upgrade", "💵 Withdraw")
    markup.row("ℹ️ Help / Support")
    return markup

# ---------- STARTUP & POLLING ----------
def start_bot():
    """Start the bot with proper error handling"""
    print("🚀 Starting MoniFlex Bot...")
    
    # Initialize database in background (non-blocking)
    try:
        init_db()
    except Exception as e:
        print(f"⚠️ Database init continued with error: {e}")
    
    # Start polling with error recovery
    while True:
        try:
            print("🤖 Bot polling started...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ Polling error: {e}")
            print("🔄 Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    start_bot()