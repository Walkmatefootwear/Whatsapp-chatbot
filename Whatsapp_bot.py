import os
import sqlite3
import requests
from flask import Flask, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
UPLOAD = os.path.join('static', 'images')
os.makedirs(UPLOAD, exist_ok=True)

ACCESS_TOKEN = 'EAARY4nQ44yoBO7r120SZBju…DEZD'  # your token
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

# Optional: WhatsApp webhook/stub can be added here if needed

if __name__ == '__main__':
    app.run(debug=True)
