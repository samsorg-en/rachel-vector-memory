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
        silent_attempts[call_sid] = 0

        response = VoiceResponse()
        first_line = memory_engine.generate_response(call_sid, "initial")["response"]

        # ✅ Strip [gather] for clean voice output
        reply = first_line.split("[gather]")[0].strip() if "[gather]" in first_line else first_line

        gather = Gather(
            input="speech",
            timeout=1,
            speechTimeout="auto",
            action="/respond_twilio",
            method="POST"
        )
        gather.say(reply, voice="Polly.Joanna")
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

        # ✅ Silence Handling
        if not user_input or user_input in ["", ".", "...", "uh", "um", "hmm"]:
            attempts = silent_attempts.get(call_sid, 0) + 1
            silent_attempts[call_sid] = attempts
            logger.info(f"🤫 Silence attempt #{attempts}")

            if attempts == 1:
                gather = Gather(input="speech", timeout=1, speechTimeout="auto", action="/respond_twilio", method="POST")
                gather.say("Can you still hear me?", voice="Polly.Joanna")
                response.append(gather)
                return str(response)

            elif attempts == 2:
                gather = Gather(input="speech", timeout=1, speechTimeout="auto", action="/respond_twilio", method="POST")
                gather.say("Just checking back in — are you still there?", voice="Polly.Joanna")
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

        # ✅ Get Rachel’s reply from memory engine
        response_data = memory_engine.generate_response(call_sid, user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")
        logger.info(f"🗣️ Rachel: {reply_text}")

        # ✅ Strip [gather] hint for clean output
        reply = reply_text.split("[gather]")[0].strip() if "[gather]" in reply_text else reply_text

        # ✅ Always listen after replying
        gather = Gather(
            input="speech",
            timeout=1,
            speechTimeout="auto",
            action="/respond_twilio",
            method="POST"
        )
        gather.say(reply, voice="Polly.Joanna")
        response.append(gather)

        return str(response)

    except Exception as e:
        logger.error(f"❌ Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Run the app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting Rachel Memory Engine on port {port}")
    app.run(host="0.0.0.0", port=port)
