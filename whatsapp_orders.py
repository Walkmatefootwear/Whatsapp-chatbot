# whatsapp_orders.py
import os
import requests
from flask import request
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")
BACKUP_TOKEN = os.getenv("BACKUP_TOKEN", "WalkBack2025")

def graph_messages_url():
    """Builds Graph API message URL"""
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_ID}/messages"

def _post_whatsapp(payload):
    """Send payload to WhatsApp Graph API"""
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    url = graph_messages_url()
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        print(f"📤 Template Sent {res.status_code}: {res.text}", flush=True)
        return res.json(), res.status_code
    except Exception as e:
        print(f"❌ WhatsApp send failed: {e}", flush=True)
        return {"error": str(e)}, 500


def register_order_routes(app):
    """
    Registers WhatsApp message endpoints:
      /send-template - for order confirmations or general messages
      /send-shipment - for shipment details
    """
    # ===========================================================
    # 1️⃣ Generic Template Sender
    # ===========================================================
    @app.get("/send-template")
    def send_template_url():
        try:
            api_key = request.args.get("api_key")
            if api_key != BACKUP_TOKEN:
                return {"ok": False, "error": "Unauthorized"}, 403

            to = request.args.get("to", "").strip().replace("+", "")
            name = request.args.get("name", "").strip()
            lang = request.args.get("lang", "en_US").strip()
            vars_csv = request.args.get("vars", "").strip()

            parameters = [{"type": "text", "text": v.strip()}
                          for v in vars_csv.split(",") if v.strip()]
            components = [{"type": "body", "parameters": parameters}] if parameters else []

            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": name,
                    "language": {"code": lang},
                    "components": components
                }
            }

            data, code = _post_whatsapp(payload)

            if code == 400 and "Number of parameters" in str(data):
                print("⚠️ Template parameter mismatch detected. Check placeholders.", flush=True)

            # Always return 200 OK to stop Meta retries
            return {"ok": code in (200, 201), "data": data, "status": code}, 200

        except Exception as e:
            print(f"❌ send-template error: {e}", flush=True)
            return {"ok": False, "error": str(e)}, 200


    # ===========================================================
    # 2️⃣ Shipment Template Sender
    # ===========================================================
    @app.get("/send-shipment")
    def send_shipment():
        try:
            api_key = request.args.get("api_key")
            if api_key != BACKUP_TOKEN:
                return {"ok": False, "error": "Unauthorized"}, 403

            to = request.args.get("to", "").replace("+", "")
            order_id = request.args.get("order_id", "").strip()
            cases = request.args.get("cases", "").strip()
            vehicle = request.args.get("vehicle", "").strip()
            driver_name = request.args.get("driver_name", "").strip()
            driver_contact = request.args.get("driver_contact", "").strip()

            # Build only the exact number of params your template needs (5)
            vars = [order_id, cases, vehicle, driver_name, driver_contact]
            parameters = [{"type": "text", "text": v}
                          for v in vars if v and v != "0"]

            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": "shipment_details",
                    "language": {"code": "en_US"},
                    "components": [{"type": "body", "parameters": parameters}]
                }
            }

            data, code = _post_whatsapp(payload)
            if code == 400 and "Number of parameters" in str(data):
                print("⚠️ Shipment template parameter mismatch detected.", flush=True)

            return {"ok": code in (200, 201), "data": data, "status": code}, 200

        except Exception as e:
            print(f"❌ send-shipment error: {e}", flush=True)
            return {"ok": False, "error": str(e)}, 200
