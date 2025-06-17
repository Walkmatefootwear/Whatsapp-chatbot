import os
import sqlite3
import requests
from flask import Flask, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
UPLOAD = os.path.join('static', 'images')
os.makedirs(UPLOAD, exist_ok=True)

ACCESS_TOKEN = 'EAARY4nQ44yoBO7r120SZBju…DEZD'  # Your actual token
PHONE_ID = '707899462402999'

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
    q = 85
    while os.path.getsize(path) > 1_000_000 and q > 10:
        img.save(path, optimize=True, quality=q)
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

# ✅ WhatsApp Webhook
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "your-verify-token")

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

            conn = sqlite3.connect('products.db')
            c = conn.cursor()

            # CASE 1: Exact color variant (main+color)
            c.execute("SELECT image, description FROM products WHERE lower(main_product || '-' || color) = ?", (user_msg,))
            row = c.fetchone()
            if row:
                image_name, caption = row
                image_path = os.path.join(UPLOAD, image_name)
                send_image(from_number, image_path, caption)
                return "Image sent", 200

            # CASE 2: Only main product number (list variants)
            c.execute("SELECT main_product, color FROM products WHERE lower(main_product) = ?", (user_msg,))
            variants = c.fetchall()
            if variants:
                opts = [f"{v[0]}-{v[1]}" for v in variants]
                reply = "Please choose a variant:\n" + "\n".join(opts)
                send_text(from_number, reply)
                return "Variants sent", 200

            send_text(from_number, "Product not found. Please enter a valid product number or variant.")
            return "Fallback sent", 200

        except Exception as e:
            print("Error:", e)
            return "Error", 500

    return "Webhook received", 200

# ✅ WhatsApp Message Functions
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
    media_url = f"https://graph.facebook.com/v19.0/{PHONE_ID}/media"
    with open(path, 'rb') as f:
        response = requests.post(
            media_url,
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            files={"file": f},
            data={"messaging_product": "whatsapp"}
        )
    media_id = response.json().get("id")
    if not media_id:
        send_text(to, "Failed to upload image.")
        return

    msg_url = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {
            "id": media_id,
            "caption": caption
        }
    }
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    requests.post(msg_url, json=payload, headers=headers)

if __name__ == '__main__':
    app.run(debug=True)
