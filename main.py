# main.py
import os
from flask import Flask
from whatsapp_chatbot import handle_webhook
from whatsapp_orders import register_order_routes
from whatsapp_admin import register_admin_routes


app = Flask(__name__)

# Register routes
handle_webhook(app)
register_order_routes(app)

@app.route("/")
def index():
    """Default route for Render health check"""
    return "Walkmate WhatsApp Bot is running 🚀", 200

@app.get("/health")
def health():
    return {
        "status": "ok",
        "routes": ["/", "/webhook", "/send-template", "/send-shipment"],
        "env_loaded": bool(os.getenv("WHATSAPP_TOKEN"))
    }, 200

if __name__ == "__main__":
    print("🚀 Walkmate WhatsApp Bot running on port",
          os.environ.get("PORT", 5000),
          flush=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
