import os
import sqlite3
import mimetypes
import requests
import shutil
from flask import Flask, request, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = 'walkmate-secret-key'
UPLOAD = 'static/Images'
LOCAL_IMAGE_PATH = 'static/images'

if not os.path.exists(UPLOAD):
    os.makedirs(UPLOAD)

@app.route('/init-upload', methods=['GET'])
def upload_images_to_disk():
    try:
        count = 0
        if not os.path.exists(LOCAL_IMAGE_PATH):
            return f"Local folder not found: {LOCAL_IMAGE_PATH}", 404
        for filename in os.listdir(LOCAL_IMAGE_PATH):
            source = os.path.join(LOCAL_IMAGE_PATH, filename)
            destination = os.path.join(UPLOAD, filename)
            if os.path.isfile(source):
                shutil.copy(source, destination)
                count += 1
        return f"{count} image(s) copied to Render disk successfully."
    except Exception as e:
        return f"Error copying images: {str(e)}"

ACCESS_TOKEN = os.getenv('WHATSAPP_TOKEN')
PHONE_ID = os.getenv('WHATSAPP_PHONE_ID', '639181935952703')
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
                            fallback_path = os.path.join(LOCAL_IMAGE_PATH, image_name)
                            if os.path.exists(fallback_path):
                                shutil.copy(fallback_path, image_path)
                        if os.path.exists(image_path):
                            send_image(from_number, image_path, caption)
                        else:
                            send_text(from_number, f"❌ Image file not found: {image_name}")
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
                print("Searching for product:", user_msg)
                c.execute("SELECT * FROM products")
                print("All products:", c.fetchall())
                c.execute("SELECT image, description FROM products WHERE lower(main_product) = ?", (user_msg,))
                rows = c.fetchall()
                print("Matching rows:", rows)
                conn.close()

                if not rows:
                    send_text(from_number, "❌ No matching product found.")
                    return "No matches", 200

                for image_name, caption in rows:
                    image_path = os.path.join(UPLOAD, image_name)
                    if not os.path.exists(image_path):
                        fallback_path = os.path.join(LOCAL_IMAGE_PATH, image_name)
                        if os.path.exists(fallback_path):
                            shutil.copy(fallback_path, image_path)
                    if os.path.exists(image_path):
                        send_image(from_number, image_path, caption)
                    else:
                        send_text(from_number, f"❌ Image not found: {image_name}")
                send_text(from_number, "✅ Done. Type another name or 1 to go back.")
                return "Product images sent", 200

            send_text(from_number, "❌ Unrecognized input. Type 'menu' to restart.")
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
    print("Sending image:", path)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        send_text(to, f"❌ File not found or empty: {path}")
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
    print("Upload response:", response.status_code, response.text)

    media_id = response.json().get("id")
    if not media_id:
        send_text(to, f"❌ Failed to upload image: {response.text}")
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

@app.route('/')
def home():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'Walkmate' and password == 'Export@2025':
            session['user'] = username
            return redirect(url_for('admin'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

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

    main_product = request.form['main_product'].strip().lower()
    option = request.form['option']
    description = request.form['description']
    mrp = request.form['mrp']
    category = request.form['category']

    file = request.files['image']
    if file and file.filename:
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD, filename)
        image = Image.open(file)
        image.save(filepath, optimize=True, quality=60)
    else:
        filename = None

    conn = sqlite3.connect('products.db')
    c = conn.cursor()
    c.execute("INSERT INTO products (main_product, option, image, description, mrp, category) VALUES (?, ?, ?, ?, ?, ?)",
              (main_product, option, filename, description, mrp, category))
    conn.commit()
    conn.close()

    return redirect(url_for('admin'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
