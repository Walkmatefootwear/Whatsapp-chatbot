import os
import sqlite3
import mimetypes
import requests
from flask import Flask, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
UPLOAD = os.path.join('static', 'images')
os.makedirs(UPLOAD, exist_ok=True)

ACCESS_TOKEN = 'EAARY4nQ44yoBO2ZAs3BZCYRfmZAJabUmHh2OBH8OhuYj1EL8ZBg6y6ZBKEilxz0IpjKforR4KqFTAvNPmDCype0uC6jKUlthGqz2ZBHg9dGb0KfZBScZCydsxlOu1uIcSBEZCMwO5MgkAOb8Rp0UGMNwZCDgISLbZAytCFSoH0bYq9qADm6SLNbKZBW9ahXTjfUZCaVZAKoZBKZCYBZAVieAATZCPuZByxKIhdeTnSDXeCgfy0ZD'
PHONE_ID = '707899462402999'
user_states = {}

def init_db():
    conn = sqlite3.connect('products.db')
    c = conn.cursor()
    c.execute('DROP TABLE IF EXISTS products')
    c.execute('''
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            main_product TEXT,
            color        TEXT,
            image        TEXT,
            description  TEXT,
            mrp          TEXT,
            category     TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def compress_image(path):
    img = Image.open(path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    ext = os.path.splitext(path)[1].lower()
    target_format = 'JPEG' if ext in ['.jpg', '.jpeg'] else 'PNG'
    q = 85
    while os.path.getsize(path) > 1_000_000 and q > 10:
        img.save(path, format=target_format, optimize=True, quality=q)
        q -= 5

@app.route('/')
def home():
    return redirect(url_for('admin'))

@app.route('/admin')
def admin():
    conn = sqlite3.connect('products.db')
    prods = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return render_template('admin.html', products=prods)

@app.route('/add', methods=['POST'])
def add_product():
    m = request.form['main_product'].strip()
    color = request.form['option'].strip()
    desc = request.form['description'].strip()
    mrp = request.form.get('mrp', '').strip()
    category = request.form.get('category', '').strip()
    img = request.files['image']
    if not img:
        return "No image", 400

    fn = secure_filename(img.filename)
    path = os.path.join(UPLOAD, fn)
    img.save(path)
    compress_image(path)

    conn = sqlite3.connect('products.db')
    conn.execute(
        "INSERT INTO products(main_product, color, image, description, mrp, category) VALUES (?, ?, ?, ?, ?, ?)",
        (m, color, fn, desc, mrp, category)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('admin', added=1))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    conn = sqlite3.connect('products.db')
    c = conn.cursor()
    if request.method == 'POST':
        m = request.form['main_product'].strip()
        color = request.form['option'].strip()
        desc = request.form['description'].strip()
        mrp = request.form.get('mrp', '').strip()
        category = request.form.get('category', '').strip()
        c.execute("""
            UPDATE products
            SET main_product=?, color=?, description=?, mrp=?, category=?
            WHERE id=?
        """, (m, color, desc, mrp, category, id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin'))
    prod = c.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
    conn.close()
    if not prod:
        return "Product not found", 404
    return render_template('edit.html', product=prod)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_product(id):
    conn = sqlite3.connect('products.db')
    c = conn.cursor()
    fn = c.execute("SELECT image FROM products WHERE id=?", (id,)).fetchone()[0]
    c.execute("DELETE FROM products WHERE id=?", (id,))
    conn.commit()
    conn.close()
    try:
        os.remove(os.path.join(UPLOAD, fn))
    except:
        pass
    return redirect(url_for('admin'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "Walkmate2025")

    if request.method == 'GET':
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
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

            if user_msg == '1' and state != 'awaiting_option':
                reply = "Please choose an option:\n1. View Catalogue\n2. View Product"
                user_states[from_number] = 'awaiting_option'
                send_text(from_number, reply)
                return "Back to menu", 200

            if user_msg in ('hi', 'hello', 'menu', 'start'):
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
                            return "Image not found", 200
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
                    reply = "✅ Back to main menu:\n1. View Catalogue\n2. View Product"
                    user_states[from_number] = 'awaiting_option'
                    send_text(from_number, reply)
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

            send_text(from_number, "I could not understand. Please reply with 'menu' to see options.")
            return "Unhandled message", 200

        except Exception as e:
            print("Error:", e)
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
