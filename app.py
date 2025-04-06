# Rachel Vector Memory - Solar Sales AI Memory Engine

import os
import sys
import json
import logging
import requests
from flask import Flask, request, jsonify
from memory_engine import MemoryEngine
from twilio.twiml.voice_response import VoiceResponse, Gather

# ✅ Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)
app = Flask(__name__)
memory_engine = MemoryEngine()

# ✅ Environment Check
def check_environment():
    required_vars = ["OPENAI_API_KEY"]
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        sys.exit(1)
    if not os.path.exists("calls"):
        os.makedirs("calls")

# ✅ Web Interface
@app.route("/")
def index():
    return '''
    <html>
        <head><title>Rachel Vector Memory Engine</title></head>
        <body>
            <h1>Rachel Vector Memory Engine</h1>
            <form action="/process" method="post"><button type="submit">Process Transcripts</button></form>
            <form action="/query" method="post">
                <textarea name="objection" rows="4" placeholder="Enter a sales objection"></textarea>
                <button type="submit">Generate Response</button>
            </form>
            <form action="/stats" method="get"><button type="submit">Show Statistics</button></form>
        </body>
    </html>
    '''

# ✅ Twilio Entry Point (Safe with Try-Catch)
@app.route("/voice", methods=["POST"])
def voice():
    try:
        response = VoiceResponse()
        gather = Gather(input="speech", timeout=5, action="/respond_twilio", method="POST")
        gather.say("Hi, this is Rachel from the solar team. Do you have a minute to chat?", voice="Polly.Joanna", language="en-US")
        response.append(gather)
        response.redirect("/voice")  # fallback loop
        return str(response)
    except Exception as e:
        logger.error(f"❌ Error in /voice: {e}")
        fallback = VoiceResponse()
        fallback.say("Sorry, something went wrong with the call. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Handle Twilio Speech Response
@app.route("/respond_twilio", methods=["POST"])
def respond_twilio():
    try:
        user_input = request.form.get("SpeechResult", "")
        logger.info(f"👂 Heard from caller: {user_input}")

        if not user_input:
            logger.info(f"👂 Lane's Debugging 1: {user_input}")
            response = VoiceResponse()
            response.say("Sorry, I didn't catch that. Could you say that again?", voice="Polly.Joanna")
            response.redirect("/voice")
            return str(response)

        logger.info(f"👂 Lane's Debugging 2: {user_input}")
        response_data = memory_engine.generate_response(user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")

        logger.info(f"👂 Lane's Debugging 3: {reply_text}")
        response = VoiceResponse()
        response.say(reply_text, voice="Polly.Joanna")

        # 🔁 Re-engage with another Gather for next input
        gather = Gather(input="speech", timeout=5, action="/respond_twilio", method="POST")
        gather.say("What else would you like to know about solar?")
        response.append(gather)
        return str(response)

    except Exception as e:
        logger.error(f"❌ Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Process Transcript Files
@app.route("/process", methods=["POST"])
def process_transcripts():
    try:
        count = memory_engine.process_transcripts()
        return f"Successfully processed {count} transcript(s)." if count > 0 else "No transcripts found."
    except Exception as e:
        return f"Error: {str(e)}"

# ✅ Manual Objection Query
@app.route("/query", methods=["POST"])
def query_objection():
    try:
        objection = request.form.get("objection", "")
        if not objection:
            return "Please provide an objection."
        response = memory_engine.generate_response(objection)
        return f"<b>Objection:</b> {objection}<br><b>Response:</b> {response.get('response', 'No response.')}"
    except Exception as e:
        return f"Error: {str(e)}"

# ✅ Vector Stats
@app.route("/stats", methods=["GET"])
def show_stats():
    try:
        stats = memory_engine.get_stats()
        return f"Stats: {json.dumps(stats)}"
    except Exception as e:
        return f"Error: {str(e)}"

# ✅ VAPI or External AI Call to Rachel Brain
@app.route("/respond", methods=["POST"])
def respond_api():
    try:
        data = request.get_json()
        user_input = data.get("text", "")
        if not user_input:
            return jsonify({"reply": "I'm sorry, I didn't catch that. Can you repeat that?"})

        response_data = memory_engine.generate_response(user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")

        # ✅ Auto-log to Google Sheets
        if "appointment set" in reply_text.lower():
            appointment_payload = {
                "customer_name": "Donna Boardman",
                "phone_number": "(623) 419-9577",
                "address": "12545 W Elwood St,, Avondale, AZ, 85323",
                "owns_home": "Yes",
                "avg_bill": "401-450",
                "credit_score": "ABOVE",
                "electric_provider": "Salt River",
                "decision_makers": "There are 2 Decision makers both will be present",
                "home_type": "Single Family",
                "bill_copy": "Yes",
                "appt_time": "Thursday, 4/3/2025 at 6pm.",
                "notes": reply_text
            }

            webhook_url = "https://script.google.com/macros/s/AKfycbyPfConiynxP89x72gRcMMDN_zrPnwjoTLLvq62J8zGZzlU_j4cNWDgvwYNarFJdMVL/exec"
            try:
                requests.post(webhook_url, json=appointment_payload)
                logger.info("✅ Appointment sent to Google Sheets")
            except Exception as send_error:
                logger.error(f"❌ Google Sheets Error: {send_error}")

        return jsonify({"reply": reply_text})
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"})

# ✅ Manual Sheet Logger (optional)
@app.route("/submit_appointment", methods=["POST"])
def submit_appointment():
    try:
        payload = request.get_json()
        webhook_url = "https://script.google.com/macros/s/AKfycbyPfConiynxP89x72gRcMMDN_zrPnwjoTLLvq62J8zGZzlU_j4cNWDgvwYNarFJdMVL/exec"
        response = requests.post(webhook_url, json=payload)

        if response.status_code == 200:
            return jsonify({"status": "✅ Appointment logged to Google Sheets"})
        else:
            return jsonify({"status": "❌ Failed", "code": response.status_code})
    except Exception as e:
        return jsonify({"status": "❌ Error", "message": str(e)})

# ✅ Start App with Auto Memory Load
if __name__ == "__main__":
    check_environment()
    logger.info("🧠 Loading call transcripts into memory...")
    memory_engine.process_transcripts()
    logger.info("✅ Rachel's memory is ready!")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
