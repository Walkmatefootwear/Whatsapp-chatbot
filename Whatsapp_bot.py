import os
import sqlite3
import requests
from flask import Flask, request, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

load_dotenv()

app = Flask(__name__)
app.secret_key = 'walkmate-secret-key'

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

ACCESS_TOKEN = os.getenv('WHATSAPP_TOKEN')
PHONE_ID = os.getenv('WHATSAPP_PHONE_ID')
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Walkmate2025")

user_states = {}

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

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Verification token mismatch", 403

    if request.method == 'POST':
        data = request.get_json()
        print("✅ Incoming Webhook:", data)

        try:
            entry = data['entry'][0]
            value = entry['changes'][0]['value']
            messages = value.get('messages')
            if not messages:
                return "No message", 200

            msg = messages[0]
            from_number = msg['from']

            # Handle message types
            user_msg = ""
            if msg['type'] == 'text':
                user_msg = msg['text']['body']
            elif msg['type'] == 'button':
                user_msg = msg['button']['payload']
            else:
                send_text(from_number, "❌ Unsupported message type.")
                return "Unsupported", 200

            # Normalize message
            try:
                user_msg = user_msg.encode('utf-16', 'surrogatepass').decode('utf-16').strip().lower()
            except Exception as e:
                print("❌ Unicode decode error:", e)
                user_msg = ""

            state = user_states.get(from_number)

            if user_msg in ('hi', 'hello'):
                send_text(from_number, "Hi 👋, welcome to Walkmate!\nPlease reply with \"2\" to get product images.")
                user_states[from_number] = 'awaiting_2'
                return "Greeting sent", 200

            if user_msg == '2' and state == 'awaiting_2':
                send_text(from_number, "Please enter the article number (e.g., 2205)")
                user_states[from_number] = 'awaiting_article'
                return "Prompted for article", 200

            if state == 'awaiting_article':
                conn = sqlite3.connect('products.db')
                c = conn.cursor()
                c.execute("SELECT image, description FROM products WHERE main_product = ?", (user_msg,))
                rows = c.fetchall()
                conn.close()

                if rows:
                    for image_url, desc in rows:
                        send_image(from_number, image_url, desc)
                else:
                    send_text(from_number, f"No product found with article number '{user_msg}'.")

                user_states.pop(from_number, None)
                return "Product(s) sent", 200

            # Fallback
            send_text(from_number, "Unrecognized input. Please type 'hi' to start.")
            return "Fallback sent", 200

        except Exception as e:
            print("❌ Webhook error:", e)
            return "Internal Error", 500

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
    res = requests.post(url, json=payload, headers=headers)
    print("📨 Text sent:", res.status_code, res.text)

def send_image(to, image_url, caption):
    if not image_url or not image_url.startswith("http"):
        send_text(to, "❌ Invalid image URL.")
        return

    media_upload = {
        "messaging_product": "whatsapp",
        "type": "image",
        "url": image_url
    }

    upload = requests.post(
        f"https://graph.facebook.com/v19.0/{PHONE_ID}/media",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        data=media_upload
    )

    response_data = upload.json()
    media_id = response_data.get("id")
    if not media_id:
        send_text(to, f"❌ Failed to send image.\n{upload.text}")
        return

    message_payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {"id": media_id, "caption": caption}
    }

    send_res = requests.post(
        f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"},
        json=message_payload
    )

    print("📤 Image sent:", send_res.status_code, send_res.text)

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
        conn.execute("INSERT INTO products (main_product, option, image, description, mrp, category) VALUES (?, ?, ?, ?, ?, ?)",
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

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
