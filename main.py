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

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Estado de cada usuario
estados = {}
conversaciones = {}

SYSTEM_NOVEDAD = """Eres el Agente SENA Metalmecánica del Centro Nacional Colombo Alemán, Barranquilla.

Cuando recibes una novedad sobre un aprendiz, respondes SIEMPRE con este formato exacto:

---
🎓 *ANÁLISIS DE NOVEDAD*
*Aprendiz:* [nombre]
*Ficha:* [codigo o PENDIENTE]
*Trimestre:* [T1/T2/T3/T4-año]

📋 *SITUACIÓN:*
[Explica brevemente la situación y su gravedad]

⚖️ *NORMA APLICABLE:*
[Cita el artículo exacto del Acuerdo 0009 de 2024]

✅ *PROCEDIMIENTO COMO INSTRUCTOR:*
1. [Paso 1]
2. [Paso 2]
3. [Paso 3]

📄 *DOCUMENTO A GENERAR:* [nombre del documento]
---

REGLAS DEL ACUERDO 0009 DE 2024:
- Art. 15: Asistencia mínima del 80%
- Art. 16: 3+ ausencias injustificadas → Llamado de Atención tipo 1
- Art. 17: 5+ ausencias injustificadas → Llamado tipo 2 + Plan de Mejoramiento
- Art. 18: +20% inasistencias → riesgo de desvinculación
- Art. 22: Nota mínima aprobatoria 3.0
- Art. 23: Nota < 3.0 → Plan de Mejoramiento obligatorio
- Art. 24: No supera Plan de Mejoramiento → Acta Extraordinaria
- Art. 25: Nota >= 4.5 en todas → Reconocimiento
- Art. 28: Mínimo 60% de evidencias por competencia
- Art. 29: < 60% evidencias → Plan de Mejoramiento
- Art. 35: Plan Concertado se firma al inicio de cada trimestre

Usa el trimestre actual si no viene en el mensaje (hoy es """ + datetime.now().strftime("%B %Y") + """).
Responde en español, profesional y directo."""

SYSTEM_REGLAMENTO = """Eres un experto en el reglamento SENA, específicamente el Acuerdo 0009 de 2024.
Cuando te pregunten sobre el reglamento, citas el artículo exacto y explicas su aplicación práctica.
Responde en español, claro y conciso."""

def get_trimestre_actual():
    mes = datetime.now().month
    year = datetime.now().year
    if mes <= 3: return f"T1-{year}"
    elif mes <= 6: return f"T2-{year}"
    elif mes <= 9: return f"T3-{year}"
    else: return f"T4-{year}"

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=30)
        logger.info(f"Telegram: {r.status_code}")
        if r.status_code != 200:
            payload2 = {"chat_id": chat_id, "text": text.replace("*","").replace("_","").replace("`","")}
            if reply_markup:
                payload2["reply_markup"] = json.dumps(reply_markup)
            requests.post(f"{TELEGRAM_API}/sendMessage", json=payload2, timeout=30)
    except Exception as e:
        logger.error(f"Error send: {e}")

def send_typing(chat_id):
    try:
        requests.post(f"{TELEGRAM_API}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except: pass

def answer_callback(callback_id):
    try:
        requests.post(f"{TELEGRAM_API}/answerCallbackQuery", json={"callback_query_id": callback_id}, timeout=10)
    except: pass

def menu_principal(chat_id):
    estados[chat_id] = {"modo": "menu"}
    send_message(chat_id,
        "👋 Bienvenido al *Agente SENA Metalmecánica*\n\n¿Qué deseas hacer?",
        reply_markup={
            "inline_keyboard": [
                [{"text": "📊 Seguimiento a la Formación", "callback_data": "menu_seguimiento"}],
                [{"text": "📖 Consultar Reglamento", "callback_data": "menu_reglamento"}],
                [{"text": "📝 Generar Plan Concertado", "callback_data": "menu_plan"}]
            ]
        }
    )

def consultar_groq(mensajes, system):
    try:
        messages = [{"role": "system", "content": system}] + mensajes
        r = requests.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": messages, "max_tokens": 1000, "temperature": 0.2},
            timeout=30
        )
        data = r.json()
        if r.status_code != 200:
            logger.error(f"Groq error: {data}")
            return None
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Groq exception: {e}")
        return None

def procesar_seguimiento(chat_id, text):
    if chat_id not in conversaciones:
        conversaciones[chat_id] = []
    conversaciones[chat_id].append({"role": "user", "content": text})
    if len(conversaciones[chat_id]) > 10:
        conversaciones[chat_id] = conversaciones[chat_id][-10:]

    send_typing(chat_id)
    respuesta = consultar_groq(conversaciones[chat_id], SYSTEM_NOVEDAD)

    if not respuesta:
        send_message(chat_id, "Error procesando. Intenta de nuevo.")
        return

    conversaciones[chat_id].append({"role": "assistant", "content": respuesta})

    # Detectar qué documento sugiere
    doc = "documento"
    if "llamado de atención" in respuesta.lower(): doc = "llamado"
    elif "plan de mejoramiento" in respuesta.lower(): doc = "plan_mejora"
    elif "acta extraordinaria" in respuesta.lower(): doc = "acta"
    elif "reconocimiento" in respuesta.lower(): doc = "reconocimiento"
    elif "plan concertado" in respuesta.lower(): doc = "plan_concertado"

    estados[chat_id]["doc_sugerido"] = doc
    estados[chat_id]["ultimo_analisis"] = respuesta

    send_message(chat_id, respuesta,
        reply_markup={
            "inline_keyboard": [
                [{"text": "✅ Generar documento", "callback_data": f"generar_{doc}"},
                 {"text": "🔄 Nueva novedad", "callback_data": "nueva_novedad"}],
                [{"text": "🏠 Menú principal", "callback_data": "menu_principal"}]
            ]
        }
    )

def procesar_reglamento(chat_id, text):
    if chat_id not in conversaciones:
        conversaciones[chat_id] = []
    conversaciones[chat_id].append({"role": "user", "content": text})

    send_typing(chat_id)
    respuesta = consultar_groq(conversaciones[chat_id], SYSTEM_REGLAMENTO)

    if not respuesta:
        send_message(chat_id, "Error procesando. Intenta de nuevo.")
        return

    conversaciones[chat_id].append({"role": "assistant", "content": respuesta})
    send_message(chat_id, respuesta,
        reply_markup={
            "inline_keyboard": [
                [{"text": "❓ Otra consulta", "callback_data": "menu_reglamento"}],
                [{"text": "🏠 Menú principal", "callback_data": "menu_principal"}]
            ]
        }
    )

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        logger.info(f"Webhook data keys: {list(data.keys())}")

        # Manejar callback de botones
        if "callback_query" in data:
            cb = data["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            cb_data = cb["data"]
            answer_callback(cb["id"])

            if cb_data == "menu_principal":
                conversaciones.pop(chat_id, None)
                menu_principal(chat_id)

            elif cb_data == "menu_seguimiento":
                estados[chat_id] = {"modo": "seguimiento"}
                conversaciones[chat_id] = []
                send_message(chat_id,
                    "📊 *Seguimiento a la Formación*\n\n"
                    "Descríbeme la novedad del aprendiz:\n\n"
                    "_Ejemplo: Aprendiz Carlos Gómez, ficha PCMCNC-5, tiene 4 fallas injustificadas este trimestre_"
                )

            elif cb_data == "menu_reglamento":
                estados[chat_id] = {"modo": "reglamento"}
                conversaciones[chat_id] = []
                send_message(chat_id,
                    "📖 *Consulta del Reglamento*\n\n"
                    "¿Qué deseas consultar del Acuerdo 0009 de 2024?\n\n"
                    "_Ejemplo: ¿Cuántas fallas justifican un llamado de atención?_"
                )

            elif cb_data == "menu_plan":
                estados[chat_id] = {"modo": "plan", "paso": "esperar_juicios"}
                conversaciones.pop(chat_id, None)
                send_message(chat_id,
                    "📝 *Generar Plan Concertado*\n\n"
                    "Por favor adjunta el archivo de *Juicios Evaluativos* (Excel o ZIP) de la ficha.\n\n"
                    "El agente extraerá automáticamente:\n"
                    "• Programa de formación\n"
                    "• Número de ficha\n"
                    "• Proyectos y actividades\n"
                    "• Lista de aprendices"
                )

            elif cb_data == "nueva_novedad":
                estados[chat_id] = {"modo": "seguimiento"}
                conversaciones[chat_id] = []
                send_message(chat_id, "📊 Cuéntame la nueva novedad:")

            elif cb_data.startswith("generar_"):
                tipo_doc = cb_data.replace("generar_", "")
                nombres_doc = {
                    "llamado": "Llamado de Atención",
                    "plan_mejora": "Plan de Mejoramiento",
                    "acta": "Acta Extraordinaria",
                    "reconocimiento": "Reconocimiento",
                    "plan_concertado": "Plan Concertado"
                }
                nombre = nombres_doc.get(tipo_doc, "Documento")
                fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
                send_message(chat_id,
                    f"📄 *{nombre} generado*\n\n"
                    f"✅ Documento registrado el {fecha}\n"
                    f"📁 Se guardará en OneDrive cuando la conexión esté activa.\n\n"
                    f"_Próximamente: generación automática del PDF y guardado directo en OneDrive._",
                    reply_markup={
                        "inline_keyboard": [
                            [{"text": "📊 Nueva novedad", "callback_data": "nueva_novedad"}],
                            [{"text": "🏠 Menú principal", "callback_data": "menu_principal"}]
                        ]
                    }
                )

            return jsonify({"ok": True})

        # Manejar mensajes de texto
        if "message" not in data:
            return jsonify({"ok": True})

        message = data["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        user = message.get("from", {})
        username = user.get("username", "")

        logger.info(f"Mensaje de @{username}: {text}")

        if not text:
            return jsonify({"ok": True})

        if text in ["/start", "/menu"]:
            conversaciones.pop(chat_id, None)
            menu_principal(chat_id)
            return jsonify({"ok": True})

        if text == "/nuevo":
            conversaciones.pop(chat_id, None)
            menu_principal(chat_id)
            return jsonify({"ok": True})

        # Enrutar según modo
        modo = estados.get(chat_id, {}).get("modo", "menu")

        if modo == "seguimiento":
            procesar_seguimiento(chat_id, text)
        elif modo == "reglamento":
            procesar_reglamento(chat_id, text)
        elif modo == "plan":
            send_message(chat_id,
                "📎 Por favor adjunta el archivo Excel o ZIP de Juicios Evaluativos.\n\n"
                "_(Función de lectura de archivos en desarrollo)_",
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "🏠 Menú principal", "callback_data": "menu_principal"}]
                    ]
                }
            )
        else:
            menu_principal(chat_id)

        return jsonify({"ok": True})

    except Exception as e:
        logger.error(f"Error webhook: {e}")
        return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Agente SENA activo", "bot": "@AgenteMecanizadoSena_bot"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
