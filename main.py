import os
import json
import logging
import requests
from flask import Flask, request, jsonify
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ALLOWED_USERS = os.environ.get("ALLOWED_USERS", "").split(",")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

conversaciones = {}

SYSTEM_PROMPT = """Eres el Agente SENA Metalmecánica, asistente del área de Metalmecánica del Centro Nacional Colombo Alemán, Barranquilla.

Ayudas a instructores a gestionar novedades y generar documentos oficiales SENA.

DOCUMENTOS QUE GESTIONAS:
1. Llamado de Atención - ausencias o incumplimientos
2. Plan de Mejoramiento - notas bajas o falta de evidencias
3. Plan Concertado - acuerdo pedagógico
4. Seguimiento a la Formación - asistencia y avance
5. Acta Extraordinaria - situaciones especiales
6. Reconocimiento - desempeño destacado
7. Consulta Reglamento - Acuerdo 0009 de 2024

REGLAS ACUERDO 0009 DE 2024:
- 3 o más ausencias injustificadas → Llamado de Atención tipo 1
- 5 o más ausencias injustificadas → Llamado tipo 2 + Plan de Mejoramiento
- Nota menor a 3.0 → Plan de Mejoramiento obligatorio
- Más del 40% de evidencias sin entregar → Plan de Mejoramiento
- Nota mayor o igual a 4.5 en todas → Reconocimiento

TRIMESTRES: T1 enero-marzo, T2 abril-junio, T3 julio-septiembre, T4 octubre-diciembre

INSTRUCCIONES:
- Identifica nombre del aprendiz y ficha del mensaje
- Si no viene trimestre pregunta: cual trimestre T1 T2 T3 o T4
- Aplica reglas y propone documento
- Confirma antes de generar
- Cuando el instructor confirme generacion incluye al final exactamente: [ACCION:{"tipo":"llamado","aprendiz":"Juan Perez","ficha":"PCMCNC-5","trimestre":"T2-2026"}]
- Tipos validos: llamado, plan_mejora, plan_concertado, acta, reconocimiento, seguimiento
- Responde en español, breve y directo
- Para preguntas del reglamento responde basandote en el Acuerdo 0009 de 2024

INSTRUCTORES: Aramis Vitola, Carlos Charris, Carlos Sabalza, Wilfrido Romero, Ana Maria Barrios, Omar Pardey"""

def get_trimestre_actual():
    mes = datetime.now().month
    year = datetime.now().year
    if mes <= 3: return f"T1-{year}"
    elif mes <= 6: return f"T2-{year}"
    elif mes <= 9: return f"T3-{year}"
    else: return f"T4-{year}"

def send_telegram_message(chat_id, text):
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=30)
        logger.info(f"Telegram response: {r.status_code} - {r.text[:100]}")
    except Exception as e:
        logger.error(f"Error Telegram: {e}")

def send_typing(chat_id):
    try:
        requests.post(f"{TELEGRAM_API}/sendChatAction", json={
            "chat_id": chat_id, "action": "typing"
        }, timeout=10)
    except:
        pass

def consultar_groq(chat_id, mensaje_usuario):
    if chat_id not in conversaciones:
        conversaciones[chat_id] = []

    conversaciones[chat_id].append({
        "role": "user",
        "content": mensaje_usuario
    })

    if len(conversaciones[chat_id]) > 20:
        conversaciones[chat_id] = conversaciones[chat_id][-20:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversaciones[chat_id]

    try:
        response = requests.post(GROQ_URL, 
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "max_tokens": 800,
                "temperature": 0.3
            },
            timeout=30
        )
        
        logger.info(f"Groq status: {response.status_code}")
        data = response.json()

        if response.status_code != 200:
            logger.error(f"Groq error: {data}")
            return "Error procesando tu solicitud. Intenta de nuevo.", None

        respuesta_completa = data["choices"][0]["message"]["content"]
        respuesta_limpia = respuesta_completa
        ruta_guardado = None

        if "[ACCION:" in respuesta_completa:
            try:
                inicio = respuesta_completa.index("[ACCION:")
                fin = respuesta_completa.index("]", inicio) + 1
                accion_str = respuesta_completa[inicio+8:fin-1]
                respuesta_limpia = respuesta_completa[:inicio].strip()
                accion = json.loads(accion_str)
                tipo = accion.get("tipo", "doc")
                aprendiz = accion.get("aprendiz", "Aprendiz")
                ficha = accion.get("ficha", "sin-ficha")
                trimestre = accion.get("trimestre", get_trimestre_actual())
                apellido = aprendiz.split()[-1]
                fecha = datetime.now().strftime("%Y%m%d")
                nombres = {
                    "llamado": f"Llamado_{apellido}_{fecha}.pdf",
                    "plan_mejora": f"PlanMejora_{apellido}_{fecha}.pdf",
                    "plan_concertado": f"PlanConcertado_{apellido}_{fecha}.pdf",
                    "acta": f"Acta_{fecha}.pdf",
                    "reconocimiento": f"Reconocimiento_{apellido}_{fecha}.pdf",
                    "seguimiento": f"Seguimiento_{fecha}.xlsx"
                }
                nombre_archivo = nombres.get(tipo, f"Documento_{fecha}.pdf")
                ruta_guardado = f"SENA-Agente/Fichas/{ficha}/{trimestre}/{nombre_archivo}"
            except Exception as e:
                logger.error(f"Error parseando accion: {e}")

        conversaciones[chat_id].append({
            "role": "assistant",
            "content": respuesta_limpia
        })

        return respuesta_limpia, ruta_guardado

    except Exception as e:
        logger.error(f"Error Groq: {e}")
        return "Error de conexion. Intenta de nuevo.", None

def es_autorizado(username, user_id):
    if not ALLOWED_USERS or ALLOWED_USERS == [""]:
        return True
    return username in ALLOWED_USERS or str(user_id) in ALLOWED_USERS

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        if not data or "message" not in data:
            return jsonify({"ok": True})

        message = data["message"]
        chat_id = message["chat"]["id"]
        user = message.get("from", {})
        username = user.get("username", "")
        user_id = user.get("id", "")
        text = message.get("text", "")

        logger.info(f"Mensaje de @{username} (id:{user_id}): {text}")

        if not text:
            return jsonify({"ok": True})

        if text == "/start":
            send_telegram_message(chat_id,
                "Hola! Soy el *Agente SENA Metalmecanica*.\n\n"
                "Gestiono novedades y documentos oficiales.\n\n"
                "Ejemplo:\n"
                "_Aprendiz Juan Perez, ficha PCMCNC-5, tiene 4 fallas injustificadas_\n\n"
                "/nuevo - Reiniciar conversacion\n"
                "/ayuda - Ver funciones"
            )
            return jsonify({"ok": True})

        if text == "/nuevo":
            conversaciones.pop(chat_id, None)
            send_telegram_message(chat_id, "Conversacion reiniciada. Cuentame la novedad.")
            return jsonify({"ok": True})

        if text == "/ayuda":
            send_telegram_message(chat_id,
                "*Puedo generar:*\n"
                "- Llamado de Atencion\n"
                "- Plan de Mejoramiento\n"
                "- Plan Concertado\n"
                "- Acta Extraordinaria\n"
                "- Reconocimiento\n\n"
                "*Y consultar:*\n"
                "- Seguimiento de ficha\n"
                "- Reglamento Acuerdo 0009"
            )
            return jsonify({"ok": True})

        if not es_autorizado(username, user_id):
            send_telegram_message(chat_id, "No tienes autorizacion. Contacta a Aramis Vitola.")
            return jsonify({"ok": True})

        send_typing(chat_id)
        respuesta, ruta = consultar_groq(chat_id, text)

        if ruta:
            respuesta += f"\n\n📁 Guardado en:\n`{ruta}`"

        send_telegram_message(chat_id, respuesta)
        return jsonify({"ok": True})

    except Exception as e:
        logger.error(f"Error webhook: {e}")
        return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Agente SENA activo", "bot": "@AgenteMecanizadoSena_bot", "model": "groq/llama-3.3-70b"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
