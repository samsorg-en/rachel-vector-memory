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

# ✅ Twilio Entry Point (Starts the call)
@app.route("/voice", methods=["POST"])
def voice():
    try:
        memory_engine.reset_script()  # 🧠 Reset for new call
        response = VoiceResponse()
        gather = Gather(input="speech", timeout=5, action="/respond_twilio", method="POST")
        gather.say("Hi, this is Rachel from the solar team. Do you have a minute to chat?", voice="Polly.Joanna")
        response.append(gather)
        response.redirect("/voice")  # fallback if no speech
        return str(response)
    except Exception as e:
        logger.error(f"❌ Error in /voice: {e}")
        fallback = VoiceResponse()
        fallback.say("Sorry, something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Handle Twilio Response (During the call)
@app.route("/respond_twilio", methods=["POST"])
def respond_twilio():
    try:
        user_input = request.form.get("SpeechResult", "")
        logger.info(f"👂 Heard from caller: {user_input}")

        if not user_input:
            logger.info("👂 Lane's Debugging 1: EMPTY input")
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

        gather = Gather(input="speech", timeout=5, action="/respond_twilio", method="POST")
        gather.say("What else would you like to know about solar?", voice="Polly.Joanna")
        response.append(gather)

        return str(response)
    except Exception as e:
        logger.error(f"❌ Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Required for Fly.io to keep app alive!
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting Rachel Memory Engine on port {port}")
    app.run(host="0.0.0.0", port=port)
