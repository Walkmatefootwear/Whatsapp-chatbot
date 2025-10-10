# Tiny Webhook Usage

## Text (inside 24h window)
curl -G "https://YOUR_DOMAIN/send-whatsapp"   --data-urlencode "api_key=REPLACE_WITH_BACKUP_TOKEN"   --data-urlencode "to=91XXXXXXXXXX"   --data-urlencode "text=Order Confirmed: ORD-1023"

## Template (outside 24h)
curl -G "https://YOUR_DOMAIN/send-template"   --data-urlencode "api_key=REPLACE_WITH_BACKUP_TOKEN"   --data-urlencode "to=91XXXXXXXXXX"   --data-urlencode "name=order_update"   --data-urlencode "lang=en"   --data-urlencode "vars=Rahul,ORD-1023,Confirmed,₹1250,https://track.example.com/ORD-1023"
