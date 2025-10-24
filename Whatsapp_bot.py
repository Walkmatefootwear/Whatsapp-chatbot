# Whatsapp_bot.py

import os
import sqlite3
import time
import requests
from requests import RequestException
import pandas as pd
from io import BytesIO
from urllib.parse import unquote_plus
from flask import Flask, request, redirect, url_for, render_template, session, send_file
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

load_dotenv()

app = Flask(__name__)
app.secret_key = "walkmate-secret-key"

# ===== Cloudinary =====
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# ===== WhatsApp / Env =====
ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Walkmate2025")
BACKUP_TOKEN = os.getenv("BACKUP_TOKEN")  # used as simple API key for URL triggers
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")

def graph_messages_url():
    if not PHONE_ID:
        raise RuntimeError("WHATSAPP_PHONE_ID is not set in environment")
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_ID}/messages"

# ===== Database (portable defaults; works on Render without a disk) =====
BASE_DIR = os.path.abspath(os.path.dirname(__file__))  # e.g. /opt/render/project/src
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))  # default ./data
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "products.db"))

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

def get_user_state(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT state, last_updated FROM user_state WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        state, last_updated = result
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

# ===== WhatsApp Send Helpers =====
def send_text(to, message):
    url = graph_messages_url()
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        print("📨 Text sent:", res.status_code, res.text)
    except RequestException as e:
        print("❌ Text send network error:", type(e).__name__, str(e))

def send_image(to, image_url, caption):
    url = graph_messages_url()
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {"link": image_url, "caption": caption}
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        print("📨 Image sent:", res.status_code, res.text)
        if res.status_code != 200:
            send_text(to, f"❌ Failed to send image.\n{res.text}")
    except RequestException as e:
        print("❌ Image send network error:", type(e).__name__, str(e))

def send_button_message(to, body, buttons):
    url = graph_messages_url()
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": buttons}
        }
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        print("🔹 Button message sent:", res.status_code, res.text)
    except RequestException as e:
        print("❌ Button send network error:", type(e).__name__, str(e))

# ===== Enhanced WhatsApp Poster with full logs =====
def _post_whatsapp(payload):
    """
    Enhanced sender: sends payload to WhatsApp Graph API and logs everything clearly.
    """
    if not ACCESS_TOKEN or not PHONE_ID:
        return {"ok": False, "error": "Missing WHATSAPP_TOKEN or WHATSAPP_PHONE_ID in .env"}, 500

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    url = graph_messages_url()

    print("\n==================== WHATSAPP API CALL ====================")
    print("📤 Sending Payload:", payload)
    print("📍 Endpoint:", url)

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        status_code = resp.status_code

        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}

        print("📩 Response Code:", status_code)
        print("📩 Response Data:", data)

        # Success summary
        if isinstance(data, dict) and "messages" in data:
            for msg in data.get("messages", []):
                print(f"✅ Message accepted by WhatsApp | ID: {msg.get('id')}")

        # Error summary
        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            print(f"❌ Meta Error {err.get('code')}: {err.get('message')}")
            details = err.get("error_data", {}).get("details")
            if details:
                print(f"   ➤ Details: {details}")

        print("===========================================================\n")
        return {"ok": status_code in (200, 201), "status": status_code, "data": data}, status_code

    except RequestException as e:
        print("❌ Network Error:", type(e).__name__, str(e))
        return {"ok": False, "error": f"NetworkError: {type(e).__name__}", "detail": str(e)}, 502

# ===== Tiny URL-Trigger Endpoints =====
@app.get("/send-whatsapp")
def send_whatsapp_url():
    """
    GET /send-whatsapp?api_key=...&to=91XXXXXXXXXX&text=Hello%20World
    Use inside 24h customer-service window (free-form text)
    """
    api_key = request.args.get("api_key")
    if not BACKUP_TOKEN or api_key != BACKUP_TOKEN:
        return {"ok": False, "error": "Unauthorized"}, 403

    to = request.args.get("to", "").strip().replace("+", "")
    text = request.args.get("text", "").strip()
    if not to or not text:
        return {"ok": False, "error": "Missing 'to' or 'text' query param"}, 400

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": unquote_plus(text)}
    }
    print("➡️  Outbound payload (text):", payload)
    res, code = _post_whatsapp(payload)
    print("⬅️  Meta response (text):", res)
    return res, code

@app.get("/send-template")
def send_template_url():
    """
    Universal WhatsApp template sender with detailed logs.
    Example:
      /send-template?api_key=WalkBack2025
                    &to=919972835890
                    &name=shipment_details
                    &lang=en_US
                    &vars=12524,300,KA09B1452,Raju Somu,9865252142
    """
    api_key = request.args.get("api_key")
    if not BACKUP_TOKEN or api_key != BACKUP_TOKEN:
        return {"ok": False, "error": "Unauthorized"}, 403

    # Clean inputs
    to = request.args.get("to", "").strip().replace("+", "")
    name = request.args.get("name", "").strip()
    lang = request.args.get("lang", "en_US").strip()
    vars_csv = request.args.get("vars", "").strip()
    policy = request.args.get("policy", "deterministic").strip()

    if not to or not name:
        print("❌ Missing required query params: 'to' or 'name'")
        return {"ok": False, "error": "Missing 'to' or 'name' query param"}, 400

    # Prepare parameters (BODY)
    parameters = []
    if vars_csv:
        for v in vars_csv.split(","):
            v = v.strip()
            if v:
                parameters.append({"type": "text", "text": v})

    components = []
    if parameters:
        components.append({"type": "body", "parameters": parameters})

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": name,
            "language": {"code": lang, "policy": policy},
            "components": components
        }
    }

    print("\n➡️ Outbound TEMPLATE MESSAGE")
    print(f"   To: {to}")
    print(f"   Template: {name}")
    print(f"   Language: {lang}")
    print(f"   Variables: {vars_csv if vars_csv else '(none)'}")

    res, code = _post_whatsapp(payload)

    if res.get("ok"):
        print(f"✅ TEMPLATE SENT SUCCESSFULLY | HTTP {code}")
    else:
        print(f"❌ TEMPLATE SEND FAILED | HTTP {code}")
    print("-----------------------------------------------------------\n")

    return res, code

# ---- Dedicated endpoint for your 'shipment_details' template ----
@app.get("/send-shipment")
def send_shipment():
    """
    Safer, explicit sender for template 'shipment_details' (en), 5 body vars:
    {{order_id}}, {{cases}}, {{vehicle_number}}, {{driver_name}}, {{driver_contact}}

    Example:
    /send-shipment?api_key=...&to=91XXXXXXXXXX&order_id=12524&cases=300&vehicle=KA09B1452&driver_name=Raju%20Somu&driver_contact=9865252142
    """
    api_key = request.args.get("api_key")
    if not BACKUP_TOKEN or api_key != BACKUP_TOKEN:
        return {"ok": False, "error": "Unauthorized"}, 403

    to = (request.args.get("to", "") or "").strip().replace("+", "")
    order_id = (request.args.get("order_id", "") or "").strip()
    cases = (request.args.get("cases", "") or "").strip()
    vehicle = (request.args.get("vehicle", "") or "").strip()
    driver_name = (request.args.get("driver_name", "") or "").strip()
    driver_contact = (request.args.get("driver_contact", "") or "").strip()

    if not to or not all([order_id, cases, vehicle, driver_name, driver_contact]):
        return {"ok": False, "error": "Missing one or more required params"}, 400

    parameters = [
        {"type": "text", "text": order_id},
        {"type": "text", "text": cases},
        {"type": "text", "text": vehicle},
        {"type": "text", "text": driver_name},
        {"type": "text", "text": driver_contact},
    ]

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": "shipment_details",
            "language": {"code": "en_US", "policy": "deterministic"},
            "components": [
                {"type": "body", "parameters": parameters}
            ]
        }
    }
    print("➡️  Outbound payload (shipment_details):", payload)
    res, code = _post_whatsapp(payload)
    print("⬅️  Meta response (shipment_details):", res)
    return res, code
# ------------------------------------------------------------------

# ===== Webhook for incoming messages (and delivery/status logs) =====
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Invalid verification token", 403

    if request.method == 'POST':
        data = request.get_json()
        print("✅ Incoming Webhook:", data)

        try:
            value = data['entry'][0]['changes'][0]['value']

            # Delivery / read / failed statuses:
            if 'statuses' in value:
                for st in value.get('statuses', []):
                    mid = st.get('id')
                    status = st.get('status')
                    ts = st.get('timestamp')
                    to = st.get('recipient_id')
                    conv = st.get('conversation', {})
                    origin = conv.get('origin', {}).get('type')
                    pricing = st.get('pricing', {})
                    print(f"📬 Status update | msg_id={mid} | to={to} | status={status} | ts={ts} | origin={origin} | pricing={pricing}")
                    if 'errors' in st:
                        for err in st['errors']:
                            print(f"   ❌ Delivery error {err.get('code')} - {err.get('title')}: {err.get('message')}")
                            details = err.get('error_data', {}).get('details')
                            if details:
                                print(f"      ➤ Details: {details}")
                return "Status received", 200

            messages = value.get('messages', [])
            if not messages:
                return "No messages", 200

            msg = messages[0]
            msg_id = msg['id']
            from_number = msg['from']
            msg_type = msg.get("type")

            if is_duplicate_message(msg_id):
                print(f"⚠️ Duplicate message {msg_id} ignored")
                return "Duplicate message", 200

            mark_message_processed(msg_id)

            user_input = ""
            if msg_type == "text" and "text" in msg:
                user_input = msg["text"].get("body", "").strip().lower()
            elif msg_type == "button" and "button" in msg:
                user_input = msg["button"].get("payload", "").strip().lower()
            elif msg_type == "interactive":
                interactive = msg.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    user_input = interactive["button_reply"]["title"].strip().lower()
                elif interactive.get("type") == "list_reply":
                    user_input = interactive["list_reply"]["title"].strip().lower()
                else:
                    send_text(from_number, "❌ Unsupported interactive type.")
                    return "Unsupported interactive type", 200
            else:
                send_text(from_number, "❌ Unsupported message type.")
                return "Unsupported message type", 200

            current_state = get_user_state(from_number)

            if user_input in ["hi", "hello"]:
                send_button_message(
                    from_number,
                    "Hi 👋, welcome to Walkmate!\nPlease reply with \"2\" to get product images.",
                    [{"type": "reply", "reply": {"id": "option_2", "title": "2"}}]
                )
                set_user_state(from_number, "awaiting_option")
                return "Greeting sent", 200

            if user_input == "2" and current_state == "awaiting_option":
                send_text(from_number, "Please enter the article number (e.g., 2205)")
                set_user_state(from_number, "awaiting_article")
                return "Asked for article number", 200

            if current_state == "awaiting_article":
                if user_input == "1":
                    send_button_message(
                        from_number,
                        "Hi 👋, welcome to Walkmate!\nPlease reply with \"2\" to get product images.",
                        [{"type": "reply", "reply": {"id": "option_2", "title": "2"}}]
                    )
                    set_user_state(from_number, "awaiting_option")
                    return "Back to menu", 200

                article = user_input
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT image, description FROM products WHERE main_product = ?", (article,))
                products = c.fetchall()
                conn.close()

                if not products:
                    send_text(from_number, "❌ No product found with article number.")
                else:
                    for image_url, description in products:
                        send_image(from_number, image_url, description)
                    send_button_message(
                        from_number,
                        "✅ Reply with 1 to go back to the main menu or enter another article number to view another product.",
                        [{"type": "reply", "reply": {"id": "go_main", "title": "1"}}]
                    )
                    set_user_state(from_number, "awaiting_article")
                return "Products sent", 200

            send_text(from_number, "Unrecognized input. Please type 'hi' to start.")
            return "Fallback sent", 200

        except Exception as e:
            print("❌ Webhook error:", e)
            return "Error", 500

# ===== Web UI & Admin =====
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'Walkmate' and request.form['password'] == 'Exp@2025@walk':
            session['user'] = 'Walkmate'
            return redirect(url_for('admin'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    if 'user' not in session:
        return redirect(url_for('login'))

    search_query = request.args.get('search', '').strip()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if search_query:
        c.execute("""
            SELECT * FROM products WHERE 
            main_product LIKE ? OR 
            option LIKE ? OR 
            description LIKE ? OR
            category LIKE ?
        """, (f"%{search_query}%",)*4)
    else:
        c.execute("SELECT * FROM products")

    prods = c.fetchall()
    conn.close()
    return render_template('admin.html', products=prods, search_query=search_query)

@app.route('/add', methods=['POST'])
def add_product():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        main_product = request.form['main_product'].strip().lower()
        option = request.form['option'].strip()
        description = request.form['description'].strip()
        mrp = request.form['mrp'].strip()
        category = request.form['category'].strip()
        file = request.files['image']

        image_url = None
        if file and file.filename:
            upload_result = cloudinary.uploader.upload(file, folder="walkmate")
            image_url = upload_result.get('secure_url')

        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO products (main_product, option, image, description, mrp, category) VALUES (?, ?, ?, ?, ?, ?)",
            (main_product, option, image_url, description, mrp, category)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('admin'))

    except Exception as e:
        print("❌ ERROR in /add:", e)
        return "Internal Server Error", 500

@app.route('/delete/<int:id>', methods=['POST'])
def delete_product(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM products WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/export_excel')
def export_excel():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT id, main_product, option, description, mrp, category FROM products", conn)
    conn.close()

    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Products')

    output.seek(0)
    return send_file(
        output,
        download_name='walkmate_products.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/download-db')
def download_db():
    token = request.args.get('token')
    if token != BACKUP_TOKEN:
        return "Unauthorized", 403

    if os.path.exists(DB_PATH):
        return send_file(DB_PATH, as_attachment=True)
    return "Database file not found", 404

# (Optional) quick health check endpoint
@app.get("/health")
def health():
    return {
        "routes": [
            "webhook",
            "send-whatsapp",
            "send-template",
            "send-shipment",
            "admin",
            "export_excel"
        ],
        "db_path": DB_PATH,
        "db_exists": os.path.exists(DB_PATH),
        "has_BACKUP_TOKEN": bool(BACKUP_TOKEN),
        "graph_version": GRAPH_API_VERSION
    }, 200


# ===== Run =====
if __name__ == '__main__':
    import sys
    import logging

    # ---- Enable live stdout logging (important for Render) ----
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG,
        format='[%(asctime)s] %(levelname)s: %(message)s'
    )

    # Make sure Python flushes every print() instantly
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    app.logger.setLevel(logging.DEBUG)
    print("🚀 WhatsApp Bot initialized successfully.")
    print("📡 Waiting for webhook messages or URL triggers...")

    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=True,
        use_reloader=False
    )


