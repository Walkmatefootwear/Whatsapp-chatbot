import os
import sqlite3
import mimetypes
import requests
from flask import Flask, request, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename
from PIL import Image
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = 'walkmate-secret-key'
UPLOAD = os.path.join('static', 'images')
os.makedirs(UPLOAD, exist_ok=True)

ACCESS_TOKEN = os.getenv('WHATSAPP_TOKEN')
PHONE_ID = os.getenv('WHATSAPP_PHONE_ID', '639181935952703')
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Walkmate2025")
user_states = {}

@app.route('/')
def home():
    return redirect(url_for('admin')) if 'user' in session else redirect(url_for('login'))

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
        main_product = request.form['main_product']
        option = request.form['option']
        description = request.form['description']
        mrp = request.form.get('mrp', '')
        category = request.form.get('category', '')
        image_file = request.files['image']

        if not image_file or not image_file.filename:
            return "Image is required.", 400

        ext = os.path.splitext(image_file.filename)[1]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        filename = secure_filename(f"{main_product}_{option}_{timestamp}{ext}")
        save_path = os.path.join(UPLOAD, filename)

        if ext.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            img = Image.open(image_file)
            img.save(save_path, optimize=True, quality=85)
        else:
            image_file.save(save_path)

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
            )""")
        c.execute("""
            INSERT INTO products (main_product, option, image, description, mrp, category)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (main_product, option, filename, description, mrp, category))
        conn.commit()
        conn.close()

        return redirect(url_for('admin', added=1))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Failed to add product: {str(e)}", 500

@app.route('/delete/<int:id>', methods=['POST'])
def delete_product(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('products.db')
    conn.execute("DELETE FROM products WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Verification token mismatch", 403

    if request.method == 'POST':
        data = request.get_json()
        print("Incoming WhatsApp message:", data)

        try:
            entry = data['entry'][0]
            changes = entry['changes'][0]
            value = changes['value']
            messages = value.get('messages')
            if not messages:
                return "No message", 200

            msg = messages[0]
            from_number = msg['from']
            user_msg = msg['text']['body'].strip().lower()
            state = user_states.get(from_number)

            if user_msg in ('hi', 'hello', 'menu', 'start') or user_msg == '1':
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
                        image_name, caption = row
                        image_path = os.path.join(UPLOAD, image_name)
                        if not os.path.exists(image_path):
                            send_text(from_number, f"❌ Image file not found:\n{image_path}")
                        else:
                            send_image(from_number, image_path, caption)
                    else:
                        send_text(from_number, "No catalogue available.")
                    user_states.pop(from_number, None)
                    return "Catalogue sent", 200

                elif user_msg == '2':
                    send_text(from_number, "Please enter the product name (e.g., 2005).")
                    user_states[from_number] = 'awaiting_article'
                    return "Asking for product name", 200
                else:
                    send_text(from_number, "I could not understand. Please reply with 1 or 2.")
                    return "Invalid option", 200

            if state == 'awaiting_article':
                if user_msg == '1':
                    user_states[from_number] = 'awaiting_option'
                    send_text(from_number, "Back to main menu:\n1. View Catalogue\n2. View Product")
                    return "Back to menu", 200

                conn = sqlite3.connect('products.db')
                c = conn.cursor()
                c.execute("SELECT image, description FROM products WHERE lower(main_product) = ?", (user_msg,))
                rows = c.fetchall()
                conn.close()

                if not rows:
                    send_text(from_number, "❌ No matching product found.\nType a correct product name or reply 1 for main menu.")
                    return "No matches", 200

                for image_name, caption in rows:
                    image_path = os.path.join(UPLOAD, image_name)
                    if os.path.exists(image_path):
                        send_image(from_number, image_path, caption)
                    else:
                        send_text(from_number, f"❌ Image not found for: {image_name}")

                send_text(from_number, "✅ Done. Type another product name to continue or 1 to go back to menu.")
                return "Product images sent", 200

            send_text(from_number, "I could not understand. Reply 'menu' to restart.")
            return "Unhandled message", 200

        except Exception as e:
            print("Webhook error:", e)
            return "Error", 500

    return "Webhook received", 200

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

def send_image(to, path, caption):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        send_text(to, f"❌ File not found or empty:\n{path}")
        return

    mime, _ = mimetypes.guess_type(path)
    if mime not in ['image/jpeg', 'image/png', 'image/webp']:
        send_text(to, f"❌ Invalid file type: {mime or 'unknown'}")
        return

    with open(path, 'rb') as f:
        response = requests.post(
            f"https://graph.facebook.com/v19.0/{PHONE_ID}/media",
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            files={"file": (os.path.basename(path), f, mime)},
            data={"messaging_product": "whatsapp"}
        )

    print("Upload result:", response.text)
    media_id = response.json().get("id")
    if not media_id:
        send_text(to, f"❌ Failed to upload image:\n{response.text}")
        return

    requests.post(
        f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages",
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": {
                "id": media_id,
                "caption": caption
            }
        }
    )

if __name__ == '__main__':
    app.run(debug=True)
