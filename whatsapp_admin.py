# whatsapp_admin.py
import os
import sqlite3
import pandas as pd
from io import BytesIO
from flask import (
    render_template, request, redirect, url_for, session, send_file
)
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

# ===== DB and Cloudinary setup =====
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "products.db"))

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

BACKUP_TOKEN = os.getenv("BACKUP_TOKEN", "WalkBack2025")

# -----------------------------------------------------------
# Register routes to Flask app
# -----------------------------------------------------------
def register_admin_routes(app):

    # ---------- Login ----------
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            if username == 'Walkmate' and password == 'Exp@2025@walk':
                session['user'] = username
                return redirect(url_for('admin_panel'))
            return render_template('login.html', error="Invalid credentials")
        return render_template('login.html')

    # ---------- Logout ----------
    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    # ---------- Admin dashboard ----------
    @app.route('/admin')
    def admin_panel():
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

        products = c.fetchall()
        conn.close()
        return render_template('admin.html', products=products, search_query=search_query)

    # ---------- Add product ----------
    @app.route('/add', methods=['POST'])
    def add_product():
        if 'user' not in session:
            return redirect(url_for('login'))
        try:
            main_product = request.form.get('main_product', '').strip().lower()
            option = request.form.get('option', '').strip()
            description = request.form.get('description', '').strip()
            mrp = request.form.get('mrp', '').strip()
            category = request.form.get('category', '').strip()
            file = request.files.get('image')

            image_url = None
            if file and file.filename:
                upload_result = cloudinary.uploader.upload(file, folder="walkmate")
                image_url = upload_result.get('secure_url')

            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                INSERT INTO products (main_product, option, image, description, mrp, category)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (main_product, option, image_url, description, mrp, category))
            conn.commit()
            conn.close()
            return redirect(url_for('admin_panel'))
        except Exception as e:
            print("❌ ERROR in /add:", e, flush=True)
            return "Internal Server Error", 500

    # ---------- Delete product ----------
    @app.route('/delete/<int:id>', methods=['POST'])
    def delete_product(id):
        if 'user' not in session:
            return redirect(url_for('login'))
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM products WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_panel'))

    # ---------- Export Excel ----------
    @app.route('/export_excel')
    def export_excel():
        if 'user' not in session:
            return redirect(url_for('login'))
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT id, main_product, option, description, mrp, category FROM products", conn)
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

    # ---------- Download DB ----------
    @app.route('/download-db')
    def download_db():
        token = request.args.get('token')
        if token != BACKUP_TOKEN:
            return "Unauthorized", 403

        if os.path.exists(DB_PATH):
            return send_file(DB_PATH, as_attachment=True)
        return "Database not found", 404
