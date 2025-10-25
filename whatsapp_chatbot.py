# whatsapp_chatbot.py
import os
import sqlite3
import time
import requests
from flask import request
from dotenv import load_dotenv

load_dotenv()

# ====== Environment Variables ======
ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Walkmate2025")

# ====== Database Setup (shared with admin panel) ======
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "products.db"))


def graph_messages_url():
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_ID}/messages"


# ====== Database Initialization ======
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            main_product TEXT,
            option TEXT,
            image TEXT,
            description TEXT,
            mrp TEXT,
            category TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_state (
            user_id TEXT PRIMARY KEY,
            state TEXT,
            last_updated INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS processed_messages (
            id TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()


init_db()

# ====== User State Management ======
def get_user_state(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT state, last_updated FROM user_state WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        state, last_updated = result
        # Reset if last update older than 10 minutes
        if time.time() - int(last_updated) > 600:
            clear_user_state(user_id)
            return None
        return state
    return None


def set_user_state(user_id, state):
    now = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("REPLACE INTO user_state (user_id, state, last_updated) VALUES (?, ?, ?)", (user_id, state, now))
    conn.commit()
    conn.close()


def clear_user_state(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM user_state WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ====== Message Deduplication ======
def is_duplicate_message(msg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM processed_messages WHERE id = ?", (msg_id,))
    exists = c.fetchone()
    conn.close()
    return exists is not None


def mark_message_processed(msg_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO processed_messages (id) VALUES (?)", (msg_id,))
    conn.commit()
    conn.close()


# ====== WhatsApp Message Sending ======
def send_text(to, message):
    url = graph_messages_url()
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        print("📨 Text sent:", res.status_code, res.text, flush=True)
    except Exception as e:
        print("❌ Text send failed:", e, flush=True)


def send_image(to, image_url, caption=""):
    url = graph_messages_url()
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {"link": image_url, "caption": caption},
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        print("🖼️ Image sent:", res.status_code, res.text, flush=True)
    except Exception as e:
        print("❌ Image send failed:", e, flush=True)


def send_button_message(to, body, buttons):
    url = graph_messages_url()
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {"type": "button", "body": {"text": body}, "action": {"buttons": buttons}},
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        print("🔘 Button message sent:", res.status_code, res.text, flush=True)
    except Exception as e:
        print("❌ Button send failed:", e, flush=True)


# ====== Webhook Route ======
def handle_webhook(app):
    @app.route("/webhook", methods=["GET", "POST"])
    def webhook():
        # --- Verification Step ---
        if request.method == "GET":
            token = request.args.get("hub.verify_token")
            challenge = request.args.get("hub.challenge")
            if token == VERIFY_TOKEN:
                print("✅ Webhook verified successfully", flush=True)
                return challenge, 200
            return "Invalid token", 403

        # --- Incoming Message Processing ---
        try:
            data = request.get_json(force=True)
            print("📩 Webhook received:", data, flush=True)

            entry = data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})

            # Handle status callbacks
            if "statuses" in value:
                for s in value["statuses"]:
                    print(f"📬 Status Update: {s.get('status')} | ID: {s.get('id')}", flush=True)
                return "Status OK", 200

            messages = value.get("messages", [])
            if not messages:
                return "No messages", 200

            msg = messages[0]
            msg_id = msg.get("id")
            from_no = msg.get("from")
            msg_type = msg.get("type")

            # Avoid duplicates
            if is_duplicate_message(msg_id):
                print(f"⚠️ Duplicate message {msg_id} ignored", flush=True)
                return "Duplicate", 200
            mark_message_processed(msg_id)

            # Extract text input
            user_input = ""
            if msg_type == "text":
                user_input = msg["text"].get("body", "").strip().lower()
            elif msg_type == "interactive":
                inter = msg["interactive"]
                if inter.get("type") == "button_reply":
                    user_input = inter["button_reply"]["title"].strip().lower()
                elif inter.get("type") == "list_reply":
                    user_input = inter["list_reply"]["title"].strip().lower()

            # --- Main Chat Logic ---
            state = get_user_state(from_no)
            print(f"👤 {from_no} | Input: {user_input} | State: {state}", flush=True)

            # Step 1: Greeting
            if user_input in ["hi", "hello"]:
                send_button_message(
                    from_no,
                    "Hi 👋, welcome to Walkmate!\nPlease reply with '2' to get product images.",
                    [{"type": "reply", "reply": {"id": "option_2", "title": "2"}}],
                )
                set_user_state(from_no, "awaiting_option")
                return "Greeting sent", 200

            # Step 2: User chooses option 2
            if user_input == "2" and state == "awaiting_option":
                send_text(from_no, "Please enter the article number (e.g., 2205)")
                set_user_state(from_no, "awaiting_article")
                return "Asked for article", 200

            # Step 3: Fetch product by article number
            if state == "awaiting_article":
                if user_input == "1":
                    send_button_message(
                        from_no,
                        "Hi 👋, welcome to Walkmate!\nPlease reply with '2' to get product images.",
                        [{"type": "reply", "reply": {"id": "option_2", "title": "2"}}],
                    )
                    set_user_state(from_no, "awaiting_option")
                    return "Returned to menu", 200

                article = user_input
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT image, description FROM products WHERE main_product=?", (article,))
                products = c.fetchall()
                conn.close()

                if not products:
                    send_text(from_no, "❌ No product found with that article number.")
                else:
                    for image_url, desc in products:
                        send_image(from_no, image_url, desc)
                    send_button_message(
                        from_no,
                        "✅ Reply with 1 to go back to the main menu or enter another article number to view another product.",
                        [{"type": "reply", "reply": {"id": "go_main", "title": "1"}}],
                    )
                    set_user_state(from_no, "awaiting_article")
                return "Products sent", 200

            # Step 4: Default fallback
            send_text(from_no, "Please type 'hi' to start again.")
            return "Fallback", 200

        except Exception as e:
            print("❌ Webhook error:", e, flush=True)
            return "Error", 200
