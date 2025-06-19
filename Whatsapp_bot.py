import os
import sqlite3
import mimetypes
import requests
from flask import Flask, request, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
app.secret_key = 'walkmate-secret-key'
UPLOAD = os.path.join('static', 'images')
os.makedirs(UPLOAD, exist_ok=True)

ACCESS_TOKEN = 'EAARY4nQ44yoBOxKwwjLltHTI5TPK6U8WR8lhflPxPIZA1ONhA5sv0xm01W3VZB3xjtZAjhgz1PB5oazKu3ak3plkjDSn65pERIPnu1HO1XqA7sMYZAjsDmpoYVkpTpqotMvY0YTv3M2r6Vo28wEERnwcR2Klhg4iajRvocmHXaRRdGOa0YSMGQZAASH6OKnikmZCbIeumJ2etdhV82rH3yzxZBVlZAU5ZC6TLrPgvwZCl1iStm13fQaryc'
PHONE_ID = '707899462402999'
user_states = {}

@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('admin'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'Walkmate' and password == 'Export@2025':
            session['user'] = username
            return redirect(url_for('admin'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/admin')
def admin():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('products.db')
    prods = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return render_template('admin.html', products=prods)

# All other routes (add/edit/delete/webhook/send_text/send_image) remain unchanged...
