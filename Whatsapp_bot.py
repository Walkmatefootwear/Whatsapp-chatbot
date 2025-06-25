import os
import sqlite3
import requests
import pandas as pd
from io import BytesIO
from flask import Flask, request, redirect, url_for, render_template, session, send_file
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

load_dotenv()

app = Flask(__name__)
app.secret_key = "walkmate-secret-key"

# Cloudinary config
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# WhatsApp credentials
ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Walkmate2025")

# Persistent path for database
DB_PATH = '/data/products.db'
os.makedirs('/data', exist_ok=True)

# =========================
# 📦 Database Initialization
# =========================
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
            state TEXT
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

# =========================
# 🧠 User State Management
# =========================
def get_user_state(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT state FROM user_state WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_user_state(user_id, state):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("REPLACE INTO user_state (user_id, state) VALUES (?, ?)", (user_id, state))
    conn.commit()
    conn.close()

def clear_user_state(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM user_state WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# =========================
# 🛡️ Duplicate Message Handling
# =========================
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

# =========================
# 🔔 WhatsApp Webhook
# =========================
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Invalid verification token", 403

    if request.method == 'POST':
        data = request.get_json()
        print("\u2705 Incoming Webhook:", data)

        try:
            value = data['entry'][0]['changes'][0]['value']
            if 'statuses' in value:
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
            else:
                send_text(from_number, "❌ Unsupported message type.")
                return "Unsupported message type", 200

            current_state = get_user_state(from_number)

            if user_input in ["hi", "hello"]:
                send_text(from_number, "Hi 👋, welcome to Walkmate!\nPlease reply with \"2\" to get product images.")
                set_user_state(from_number, "awaiting_option")
                return "Greeting sent", 200

            if user_input == "2" and current_state == "awaiting_option":
                send_text(from_number, "Please enter the article number (e.g., 2205)")
                set_user_state(from_number, "awaiting_article")
                return "Asked for article number", 200

            if current_state == "awaiting_article":
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

                clear_user_state(from_number)
                return "Products sent", 200

            send_text(from_number, "Unrecognized input. Please type 'hi' to start.")
            return "Fallback sent", 200

        except Exception as e:
            print("❌ Webhook error:", e)
            return "Error", 500

# =========================
# 📤 WhatsApp Helpers
# =========================
def send_text(to, message):
    url = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
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
    res = requests.post(url, headers=headers, json=payload)
    print("📨 Text sent:", res.status_code, res.text)

def send_image(to, image_url, caption):
    url = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
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
    res = requests.post(url, headers=headers, json=payload)
    print("📨 Image sent:", res.status_code, res.text)
    if res.status_code != 200:
        send_text(to, f"❌ Failed to send image.\n{res.text}")

# =========================
# 🔐 Admin Panel
# =========================
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'Walkmate' and request.form['password'] == 'Export@2025':
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

# =========================
# 🚀 Run the App
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
