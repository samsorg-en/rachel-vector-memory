from flask import Flask, request, send_file
from twilio.twiml.voice_response import VoiceResponse, Gather, Pause
import logging
import sys
import os
from memory_engine import MemoryEngine
from urllib.parse import quote_plus
import io
import requests

# ✅ Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ✅ Flask App Setup
app = Flask(__name__)
memory_engine = MemoryEngine()

# ✅ Silence Tracker
silent_attempts = {}

# ✅ Start Call
@app.route("/voice", methods=["POST"])
def voice():
    try:
        call_sid = request.form.get("CallSid")
        memory_engine.reset_script(call_sid)
        silent_attempts[call_sid] = 0

        response = VoiceResponse()
        first_line = memory_engine.generate_response(call_sid, "initial")["response"]
        reply = first_line.split("[gather]")[0].strip() if "[gather]" in first_line else first_line
        url_encoded_text = quote_plus(reply)

        gather = Gather(
            input="speech",
            timeout=3,
            speechTimeout="auto",
            action="/respond_twilio",
            method="POST"
        )
        gather.pause(length=1)
        gather.play(f"https://c1e683b7-68a3-4488-b9b7-6add18b2c7d7-00-2e67wml3xjfbp.spock.replit.dev/speech?text={url_encoded_text}")
        gather.pause(length=1)
        response.append(gather)
        return str(response)

    except Exception as e:
        logger.error(f"❌ Error in /voice: {e}")
        fallback = VoiceResponse()
        fallback.say("Sorry, something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Respond to User Input
@app.route("/respond_twilio", methods=["POST"])
def respond_twilio():
    try:
        call_sid = request.form.get("CallSid")
        raw_input = request.form.get("SpeechResult", "")
        user_input = raw_input.strip().lower() if raw_input else ""

        logger.info(f"👂 Heard from caller: '{user_input}'")
        response = VoiceResponse()

        # ✅ Silence Detection
        if not user_input or user_input in ["", ".", "...", "uh", "um", "hmm"]:
            attempts = silent_attempts.get(call_sid, 0) + 1
            silent_attempts[call_sid] = attempts
            logger.info(f"🤫 Silence attempt #{attempts}")

            if attempts == 1:
                gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
                gather.play("https://c1e683b7-68a3-4488-b9b7-6add18b2c7d7-00-2e67wml3xjfbp.spock.replit.dev/speech?text=Can+you+still+hear+me%3F")
                response.append(gather)
                return str(response)

            elif attempts == 2:
                gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
                gather.play("https://c1e683b7-68a3-4488-b9b7-6add18b2c7d7-00-2e67wml3xjfbp.spock.replit.dev/speech?text=Just+checking+back+in+%E2%80%94+are+you+still+there%3F")
                response.append(gather)
                return str(response)

            else:
                response.say("Okay, I’ll go ahead and try again another time. Take care!", voice="Polly.Joanna")
                response.hangup()
                silent_attempts.pop(call_sid, None)
                memory_engine.reset_script(call_sid)
                return str(response)

        # ✅ Reset silence tracker
        silent_attempts[call_sid] = 0

        # ✅ Get Response from Memory Engine
        response_data = memory_engine.generate_response(call_sid, user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")
        logger.info(f"🗣️ Rachel: {reply_text}")

        reply = reply_text.split("[gather]")[0].strip() if "[gather]" in reply_text else reply_text
        url_encoded_text = quote_plus(reply)

        # ✅ Final Gather after response
        gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
        gather.pause(length=1)
        gather.play(f"https://c1e683b7-68a3-4488-b9b7-6add18b2c7d7-00-2e67wml3xjfbp.spock.replit.dev/speech?text={url_encoded_text}")
        gather.pause(length=1)
        response.append(gather)

        return str(response)

    except Exception as e:
        logger.error(f"❌ Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ ElevenLabs Speech Endpoint
@app.route("/speech")
def speech():
    text = request.args.get("text", "")
    voice_id = "EXAVITQu4vr4xnSDxMaL"  # Rachel's voice ID
    api_key = "sk_bc11b5c020232ad11edfade246e472ffa60993e167ef2075"

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }

    response = requests.post(url, json=payload, headers=headers, stream=True)
    return send_file(io.BytesIO(response.content), mimetype="audio/mpeg")

# ✅ Run the app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting Rachel Memory Engine on port {port}")
    app.run(host="0.0.0.0", port=port)
