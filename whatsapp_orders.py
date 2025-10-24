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
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_ID}/messages"

def _post_whatsapp(payload):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    url = graph_messages_url()
    res = requests.post(url, headers=headers, json=payload, timeout=20)
    print(f"📤 Template Sent {res.status_code}: {res.text}", flush=True)
    return res.json(), res.status_code

def register_order_routes(app):
    @app.get("/send-template")
    def send_template_url():
        api_key = request.args.get("api_key")
        if api_key != BACKUP_TOKEN:
            return {"ok": False, "error": "Unauthorized"}, 403

        to = request.args.get("to", "").strip().replace("+", "")
        name = request.args.get("name", "").strip()
        lang = request.args.get("lang", "en_US").strip()
        vars_csv = request.args.get("vars", "").strip()

        parameters = [{"type": "text", "text": v.strip()} for v in vars_csv.split(",") if v.strip()]
        components = [{"type": "body", "parameters": parameters}] if parameters else []

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {"name": name, "language": {"code": lang}, "components": components}
        }

        data, code = _post_whatsapp(payload)
        return {"ok": code in (200, 201), "data": data}, code

    @app.get("/send-shipment")
    def send_shipment():
        api_key = request.args.get("api_key")
        if api_key != BACKUP_TOKEN:
            return {"ok": False, "error": "Unauthorized"}, 403

        to = request.args.get("to", "").replace("+", "")
        order_id = request.args.get("order_id")
        cases = request.args.get("cases")
        vehicle = request.args.get("vehicle")
        driver_name = request.args.get("driver_name")
        driver_contact = request.args.get("driver_contact")

        vars = [order_id, cases, vehicle, driver_name, driver_contact]
        parameters = [{"type": "text", "text": v} for v in vars if v]

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
        return {"ok": code in (200, 201), "data": data}, code
