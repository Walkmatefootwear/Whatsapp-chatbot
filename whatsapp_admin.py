# whatsapp_admin.py
import os
import sqlite3
from flask import request, render_template_string, redirect
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

load_dotenv()

# Cloudinary setup
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

DB_PATH = "walkmate.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_no TEXT UNIQUE,
            name TEXT,
            color TEXT,
            image_url TEXT
        )
    """)
    conn.commit()
    conn.close()

def register_admin_routes(app):
    init_db()

    @app.route("/admin", methods=["GET", "POST"])
    def admin_page():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        if request.method == "POST":
            article_no = request.form["article_no"].strip()
            name = request.form["name"].strip()
            color = request.form["color"].strip()
            image_file = request.files.get("image")

            image_url = None
            if image_file:
                upload_result = cloudinary.uploader.upload(image_file, folder="walkmate_products")
                image_url = upload_result.get("secure_url")

            if image_url:
                c.execute(
                    "INSERT OR REPLACE INTO products (article_no, name, color, image_url) VALUES (?, ?, ?, ?)",
                    (article_no, name, color, image_url),
                )
                conn.commit()

        c.execute("SELECT id, article_no, name, color, image_url FROM products ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()

        html = """
        <html>
        <head>
            <title>Walkmate Product Admin</title>
            <style>
                body { font-family: Arial; margin: 40px; }
                input, button { margin: 5px; padding: 8px; }
                img { height: 80px; border-radius: 6px; }
                table { border-collapse: collapse; margin-top: 20px; width: 100%; }
                th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
            </style>
        </head>
        <body>
            <h2>🩴 Walkmate Product Admin</h2>
            <form method="POST" enctype="multipart/form-data">
                <input name="article_no" placeholder="Article No" required>
                <input name="name" placeholder="Product Name">
                <input name="color" placeholder="Color">
                <input type="file" name="image" accept="image/*" required>
                <button type="submit">Upload</button>
            </form>
            <table>
                <tr><th>ID</th><th>Article</th><th>Name</th><th>Color</th><th>Image</th></tr>
                {% for r in rows %}
                <tr>
                    <td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3]}}</td>
                    <td><a href="{{r[4]}}" target="_blank"><img src="{{r[4]}}"></a></td>
                </tr>
                {% endfor %}
            </table>
        </body>
        </html>
        """
        return render_template_string(html, rows=rows)
