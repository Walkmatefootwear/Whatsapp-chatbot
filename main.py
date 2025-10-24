# main.py
from flask import Flask
from whatsapp_chatbot import handle_webhook
from whatsapp_orders import register_order_routes
import os

app = Flask(__name__)

# Register routes from other modules
handle_webhook(app)
register_order_routes(app)

@app.get("/health")
def health():
    return {"status": "ok", "routes": ["/webhook", "/send-template", "/send-shipment"]}, 200

if __name__ == "__main__":
    print("🚀 Walkmate WhatsApp Bot running...", flush=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
