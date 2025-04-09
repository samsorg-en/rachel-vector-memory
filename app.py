from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather, Pause
import logging
import sys
import os
from memory_engine import MemoryEngine
import requests

# ✅ Config
ELEVENLABS_API_KEY = "44f85f83fb0d601244a277e6278fb1be"
ELEVENLABS_VOICE_ID = "MioXIsoKIp7emOKpdXaL"

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

# ✅ ElevenLabs Text-to-Speech

def synthesize_speech(text):
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.85,
                "style": 0.45,
                "use_speaker_boost": True
            }
        }
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            with open("/tmp/response.mp3", "wb") as f:
                f.write(response.content)
            return "/tmp/response.mp3"
        else:
            logger.error(f"\u274c ElevenLabs Error: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"\u274c TTS Error: {e}")
    return None

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

        gather = Gather(
            input="speech",
            timeout=3,
            speechTimeout="auto",
            action="/respond_twilio",
            method="POST"
        )
        gather.pause(length=1)
        gather.say(reply, voice="Polly.Joanna")  # Placeholder fallback
        gather.pause(length=1)
        response.append(gather)

        return str(response)

    except Exception as e:
        logger.error(f"\u274c Error in /voice: {e}")
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

        logger.info(f"\ud83d\udde3\ufe0f Heard from caller: '{user_input}'")
        response = VoiceResponse()

        # ✅ Silence Detection
        if not user_input or user_input in ["", ".", "...", "uh", "um", "hmm"]:
            attempts = silent_attempts.get(call_sid, 0) + 1
            silent_attempts[call_sid] = attempts
            logger.info(f"\ud83e\ude2b Silence attempt #{attempts}")

            msg = "Can you still hear me?" if attempts == 1 else (
                "Just checking back in — are you still there?" if attempts == 2 else
                "Okay, I’ll go ahead and try again another time. Take care!")

            if attempts < 3:
                gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
                gather.say(msg, voice="Polly.Joanna")
                response.append(gather)
            else:
                response.say(msg, voice="Polly.Joanna")
                response.hangup()
                silent_attempts.pop(call_sid, None)
                memory_engine.reset_script(call_sid)

            return str(response)

        silent_attempts[call_sid] = 0

        response_data = memory_engine.generate_response(call_sid, user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")
        logger.info(f"\ud83d\udde3\ufe0f Rachel: {reply_text}")

        reply = reply_text.split("[gather]")[0].strip() if "[gather]" in reply_text else reply_text

        gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
        gather.pause(length=1)
        gather.say(reply, voice="Polly.Joanna")
        gather.pause(length=1)
        response.append(gather)

        return str(response)

    except Exception as e:
        logger.error(f"\u274c Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Run the app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"\ud83d\ude80 Starting Rachel Memory Engine on port {port}")
    app.run(host="0.0.0.0", port=port)
