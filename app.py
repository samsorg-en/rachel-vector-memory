from flask import Flask, request, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
import logging
import sys
import os
import requests
from memory_engine import MemoryEngine

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

# ✅ Silent Tracker
silent_attempts = {}

# ✅ Start the Call with Script
@app.route("/voice", methods=["POST"])
def voice():
    try:
        memory_engine.reset_script()
        response = VoiceResponse()
        first_line = memory_engine.generate_response("initial")["response"]

        gather = Gather(
            input="speech",
            timeout=1.5,
            action="/respond_twilio",
            method="POST"
        )
        gather.say(first_line, voice="Polly.Joanna")
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
        user_input = request.form.get("SpeechResult", "")
        logger.info(f"👂 Heard from caller: {user_input}")

        # Handle silence
        if not user_input:
            silent_attempts[call_sid] = silent_attempts.get(call_sid, 0) + 1
            logger.info(f"🤫 Silence detected: {silent_attempts[call_sid]} time(s)")

            response = VoiceResponse()

            if silent_attempts[call_sid] == 1:
                gather = Gather(input="speech", timeout=1.5, action="/respond_twilio", method="POST")
                gather.say("Can you still hear me?", voice="Polly.Joanna")
                response.append(gather)

            elif silent_attempts[call_sid] == 2:
                gather = Gather(input="speech", timeout=1.5, action="/respond_twilio", method="POST")
                gather.say("Did I lose you?", voice="Polly.Joanna")
                response.append(gather)

            elif silent_attempts[call_sid] >= 3:
                response.say("Alright, I’ll try back another time.", voice="Polly.Joanna")
                response.hangup()

            return str(response)

        # Reset silence tracker on user response
        silent_attempts[call_sid] = 0

        response_data = memory_engine.generate_response(user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")
        logger.info(f"🗣️ Rachel: {reply_text}")

        response = VoiceResponse()
        response.say(reply_text, voice="Polly.Joanna")

        # Gather next input
        gather = Gather(input="speech", timeout=1.5, action="/respond_twilio", method="POST")
        gather.say("What else would you like to know about solar?", voice="Polly.Joanna")
        response.append(gather)

        return str(response)

    except Exception as e:
        logger.error(f"❌ Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Keep Fly.io Alive
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting Rachel Memory Engine on port {port}")
    app.run(host="0.0.0.0", port=port)
