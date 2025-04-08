from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
import logging
import sys
import os
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

# ✅ Silence Tracker
silent_attempts = {}

# ✅ Start Call
@app.route("/voice", methods=["POST"])
def voice():
    try:
        call_sid = request.form.get("CallSid")
        memory_engine.reset_script(call_sid)
        silent_attempts[call_sid] = 0  # initialize silence attempts

        response = VoiceResponse()
        first_line = memory_engine.generate_response(call_sid, "initial")["response"]

        gather = Gather(
            input="speech",
            timeout=1.5,
            speechTimeout="auto",
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
        user_input = request.form.get("SpeechResult", "").strip()
        logger.info(f"👂 Heard from caller: {user_input}")

        response = VoiceResponse()

        # ✅ Silence Handling
        if not user_input:
            attempts = silent_attempts.get(call_sid, 0) + 1
            silent_attempts[call_sid] = attempts
            logger.info(f"🤫 Silence attempt #{attempts}")

            if attempts == 1:
                gather = Gather(input="speech", timeout=1.5, speechTimeout="auto", action="/respond_twilio", method="POST")
                gather.say("Can you still hear me?", voice="Polly.Joanna")
                response.append(gather)

            elif attempts == 2:
                gather = Gather(input="speech", timeout=1.5, speechTimeout="auto", action="/respond_twilio", method="POST")
                gather.say("Just checking back in — are you still there?", voice="Polly.Joanna")
                response.append(gather)

            else:
                response.say("Okay, I’ll go ahead and try again another time. Take care!", voice="Polly.Joanna")
                response.hangup()
                silent_attempts.pop(call_sid, None)
                memory_engine.reset_script(call_sid)

            return str(response)

        # ✅ Reset silence tracker if user responded
        silent_attempts[call_sid] = 0

        # ✅ Get response from script or fallback
        response_data = memory_engine.generate_response(call_sid, user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")
        logger.info(f"🗣️ Rachel: {reply_text}")

        if response_data.get("sources") == ["script"]:
            gather = Gather(input="speech", timeout=1.5, speechTimeout="auto", action="/respond_twilio", method="POST")
            gather.say(reply_text, voice="Polly.Joanna")
            response.append(gather)
        else:
            response.say(reply_text, voice="Polly.Joanna")
            response.hangup()
            memory_engine.reset_script(call_sid)

        return str(response)

    except Exception as e:
        logger.error(f"❌ Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Keep App Running
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting Rachel Memory Engine on port {port}")
    app.run(host="0.0.0.0", port=port)
