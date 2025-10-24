# whatsapp_chatbot.py
import os
import sqlite3
import time
import requests
from flask import request, Response
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Walkmate2025")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "products.db")

def graph_messages_url():
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_ID}/messages"

def send_text(to, message):
    url = graph_messages_url()
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}
    requests.post(url, headers=headers, json=payload)

def send_image(to, image_url, caption=""):
    url = graph_messages_url()
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "image",
               "image": {"link": image_url, "caption": caption}}
    requests.post(url, headers=headers, json=payload)

def handle_webhook(app):
    @app.route("/webhook", methods=["GET", "POST"])
    def webhook():
        if request.method == "GET":
            if request.args.get("hub.verify_token") == VERIFY_TOKEN:
                return request.args.get("hub.challenge"), 200
            return "Invalid verification token", 403

        try:
            data = request.get_json(force=True)
            print("📩 Webhook received:", data, flush=True)

            entry = data.get("entry", [{}])[0]
            value = entry.get("changes", [{}])[0].get("value", {})

            if "statuses" in value:
                for s in value["statuses"]:
                    print(f"📬 Status Update: {s}", flush=True)
                return Response("Status OK", 200)

            if "messages" in value:
                msg = value["messages"][0]
                from_no = msg["from"]
                msg_type = msg.get("type")
                text = ""

                if msg_type == "text":
                    text = msg["text"]["body"].strip().lower()

                if text in ["hi", "hello"]:
                    send_text(from_no, "Hi 👋 Welcome to Walkmate!\nSend article number to get product image.")
                    return Response("Hi handled", 200)

                # Example: reply with product image
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT image, description FROM products WHERE main_product=?", (text,))
                prods = c.fetchall()
                conn.close()

                if prods:
                    for image, desc in prods:
                        send_image(from_no, image, desc)
                    send_text(from_no, "✅ Send another article number to view another product.")
                else:
                    send_text(from_no, "❌ No product found. Try again.")
                return Response("Message handled", 200)

            return Response("No message", 200)

        except Exception as e:
            print("❌ Webhook error:", e, flush=True)
            return Response("Error", 200)
