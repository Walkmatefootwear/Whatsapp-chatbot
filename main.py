# main.py
import os
from flask import Flask
from whatsapp_chatbot import handle_webhook
from whatsapp_orders import register_order_routes
from whatsapp_admin import register_admin_routes   # ✅ added import

app = Flask(__name__)
app.secret_key = "walkmate-secret-key"

# ===============================
# Register routes from other modules
# ===============================
handle_webhook(app)
register_order_routes(app)
register_admin_routes(app)   # ✅ added line

# ===============================
# Default home route
# ===============================
@app.route("/")
def index():
    """Default route for Render health check"""
    return "Walkmate WhatsApp Bot is running 🚀", 200

# ===============================
# Health check route
# ===============================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "routes": ["/", "/webhook", "/send-template", "/send-shipment", "/admin"],  # ✅ include /admin
        "env_loaded": bool(os.getenv("WHATSAPP_TOKEN"))
    }, 200

# ===============================
# Entry point
# ===============================
if __name__ == "__main__":
    print("🚀 Walkmate WhatsApp Bot running on port",
          os.environ.get("PORT", 5000),
          flush=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
