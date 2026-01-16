# main.py
import os
from flask import Flask, send_file, request

from whatsapp_chatbot import handle_webhook
from whatsapp_orders import register_order_routes
from whatsapp_admin import register_admin_routes

app = Flask(__name__)
app.secret_key = "walkmate-secret-key"

# ===============================
# Register routes from other modules
# ===============================
handle_webhook(app)
register_order_routes(app)
register_admin_routes(app)

# ===============================
# TEMPORARY DB DOWNLOAD ROUTE
# ===============================
@app.route("/download-db-temp")
def download_db_temp():
    token = request.args.get("token")

    BACKUP_TOKEN = os.getenv("BACKUP_TOKEN", "WalkBack2025")
    DB_PATH = os.getenv("DB_PATH", "/data/products.db")

    if token != BACKUP_TOKEN:
        return "Unauthorized", 403

    if not os.path.exists(DB_PATH):
        return f"Database not found at {DB_PATH}", 404

    return send_file(
        DB_PATH,
        as_attachment=True,
        download_name="products_backup.db"
    )

# ===============================
# Default home route
# ===============================
@app.route("/")
def index():
    return "Walkmate WhatsApp Bot is running 🚀", 200

# ===============================
# Health check route
# ===============================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "routes": ["/", "/webhook", "/send-template", "/send-shipment", "/admin"],
        "env_loaded": bool(os.getenv("WHATSAPP_TOKEN"))
    }, 200

# ===============================
# Entry point
# ===============================
if __name__ == "__main__":
    print(
        "🚀 Walkmate WhatsApp Bot running on port",
        os.environ.get("PORT", 5000),
        flush=True
    )
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
