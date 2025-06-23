import os
import sqlite3
import requests
from flask import Flask, request, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = 'walkmate-secret-key'

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

# WhatsApp API credentials
ACCESS_TOKEN = os.getenv('WHATSAPP_TOKEN')
PHONE_ID = os.getenv('WHATSAPP_PHONE_ID')
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Walkmate2025")

user_states = {}

# Initialize DB
def init_db():
    conn = sqlite3.connect('products.db')
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
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return redirect(url_for('login'))

# ------------------- Webhook -------------------
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Verification token mismatch", 403

    if request.method == 'POST':
        data = request.get_json()
        try:
            entry = data['entry'][0]
            changes = entry['changes'][0]
            value = changes['value']
            messages = value.get('messages')
            if not messages:
                return "No message", 200

            msg = messages[0]
            from_number = msg['from']
            raw_body = msg['text']['body']

            try:
                user_msg = raw_body.encode('utf-16', 'surrogatepass').decode('utf-16').strip().lower()
            except Exception as e:
                print("❌ Unicode decode error:", e)
                user_msg = ""

            state = user_states.get(from_number)

            if user_msg in ('hi', 'hello', 'menu', '1'):
                reply = "Please choose an option:\n1. View Catalogue\n2. View Product"
                user_states[from_number] = 'awaiting_option'
                send_text(from_number, reply)
                return "Menu sent", 200

            if state == 'awaiting_option':
                if user_msg == '1':
                    conn = sqlite3.connect('products.db')
                    row = conn.execute("SELECT image, description FROM products WHERE category = 'catalogue' LIMIT 1").fetchone()
                    conn.close()
                    if row:
                        send_image(from_number, row[0], row[1])
                    else:
                        send_text(from_number, "No catalogue available.")
                    user_states.pop(from_number, None)
                    return "Catalogue sent", 200

                elif user_msg == '2':
                    send_text(from_number, "Please enter the product name (e.g., 2005).")
                    user_states[from_number] = 'awaiting_article'
                    return "Asking for product name", 200
                else:
                    send_text(from_number, "Invalid option. Reply 1 or 2.")
                    return "Invalid option", 200

            if state == 'awaiting_article':
                conn = sqlite3.connect('products.db')
                c = conn.cursor()
                c.execute("SELECT image, description FROM products WHERE lower(main_product) = ?", (user_msg,))
                rows = c.fetchall()
                conn.close()

                if not rows:
                    send_text(from_number, "❌ No matching product found.")
                    return "No matches", 200

                for image_url, caption in rows:
                    send_image(from_number, image_url, caption)

                send_text(from_number, "✅ Done. Type another name or 1 to go back.")
                return "Product images sent", 200

            send_text(from_number, "❌ Unrecognized input. Type 'menu' to restart.")
            return "Unhandled message", 200

        except Exception as e:
            print("❌ Webhook error:", e)
            return "Error", 500

# ------------------- WhatsApp Send -------------------
def send_text(to, msg):
    url = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": msg}
    }
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    requests.post(url, json=payload, headers=headers)

def send_image(to, image_url, caption):
    response = requests.post(
        f"https://graph.facebook.com/v19.0/{PHONE_ID}/media",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        data={"messaging_product": "whatsapp", "type": "image", "url": image_url}
    )

    media_id = response.json().get("id")
    if not media_id:
        send_text(to, f"❌ Image upload failed: {response.text}")
        return

    requests.post(
        f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": {"id": media_id, "caption": caption}
        }
    )

# ------------------- Admin Panel -------------------
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
    conn = sqlite3.connect('products.db')
    prods = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return render_template('admin.html', products=prods)

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

        conn = sqlite3.connect('products.db')
        c = conn.cursor()
        c.execute("INSERT INTO products (main_product, option, image, description, mrp, category) VALUES (?, ?, ?, ?, ?, ?)",
                  (main_product, option, image_url, description, mrp, category))
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
    conn = sqlite3.connect('products.db')
    conn.execute("DELETE FROM products WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

# ------------------- Run -------------------
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
