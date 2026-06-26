import os
import requests
import sys

TOKEN = os.environ.get("TELEGRAM_TOKEN") or input("Token del bot: ")
URL = input("URL de Railway (ej: https://agente-sena.up.railway.app): ").strip()

webhook_url = f"{URL}/webhook"
response = requests.post(
    f"https://api.telegram.org/bot{TOKEN}/setWebhook",
    json={"url": webhook_url}
)

data = response.json()
if data.get("ok"):
    print(f"Webhook configurado exitosamente: {webhook_url}")
else:
    print(f"Error: {data}")
