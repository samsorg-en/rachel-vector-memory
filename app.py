from flask import Flask, request, send_file, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather, Pause, Play
import logging
import sys
import os
import time
from memory_engine import MemoryEngine
import requests

# ✅ Config
ELEVENLABS_API_KEY = "sk_bc11b5c020232ad11edfade246e472ffa60993e167ef2075"
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
            filename = f"{abs(hash(text))}.mp3"
            filepath = f"/tmp/{filename}"
            with open(filepath, "wb") as f:
                f.write(response.content)

            for _ in range(10):
                if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    return url_for("serve_audio", filename=filename, _external=True)
                time.sleep(0.1)

            logger.error("❌ File write timeout — MP3 never ready.")
        else:
            logger.error(f"❌ ElevenLabs Error: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"❌ TTS Error: {e}")
    return None

# ✅ Serve Audio File
@app.route("/audio/<filename>")
def serve_audio(filename):
    path = f"/tmp/{filename}"
    if os.path.exists(path):
        return send_file(path, mimetype="audio/mpeg")
    return "Audio not found", 404

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

        audio_url = synthesize_speech(reply)
        gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
        gather.pause(length=1)
        if audio_url:
            gather.play(audio_url)
        else:
            gather.say(reply)
        gather.pause(length=1)
        response.append(gather)

        return str(response)

    except Exception as e:
        logger.error(f"❌ Error in /voice: {e}")
        fallback = VoiceResponse()
        fallback.say("Sorry, something went wrong. Please try again later.")
        return str(fallback)

# ✅ Respond to User Input
@app.route("/respond_twilio", methods=["POST"])
def respond_twilio():
    try:
        if request.is_json:
            data = request.get_json()
            call_sid = data.get("session_id", "default_sid")
            raw_input = data.get("user_input", "")
        else:
            call_sid = request.form.get("CallSid")
            raw_input = request.form.get("SpeechResult", "")

        user_input = raw_input.strip().lower() if raw_input else ""

        logger.info(f"🗣️ Heard from caller: '{user_input}'")
        response = VoiceResponse()

        if not user_input or user_input in ["", ".", "...", "uh", "um", "hmm"]:
            attempts = silent_attempts.get(call_sid, 0) + 1
            silent_attempts[call_sid] = attempts
            logger.info(f"🨫 Silence attempt #{attempts}")

            msg = "Can you still hear me?" if attempts == 1 else (
                "Just checking back in — are you still there?" if attempts == 2 else
                "Okay, I’ll go ahead and try again another time. Take care!")

            if attempts < 3:
                gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
                audio_url = synthesize_speech(msg)
                gather.pause(length=1)
                if audio_url:
                    gather.play(audio_url)
                else:
                    gather.say(msg)
                response.append(gather)
            else:
                audio_url = synthesize_speech(msg)
                if audio_url:
                    response.play(audio_url)
                else:
                    response.say(msg)
                response.hangup()
                silent_attempts.pop(call_sid, None)
                memory_engine.reset_script(call_sid)

            return str(response)

        silent_attempts[call_sid] = 0

        response_data = memory_engine.generate_response(call_sid, user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")
        logger.info(f"🗣️ Rachel: {reply_text}")

        reply = reply_text.split("[gather]")[0].strip() if "[gather]" in reply_text else reply_text

        audio_url = synthesize_speech(reply)
        gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
        gather.pause(length=1)
        if audio_url:
            gather.play(audio_url)
        else:
            gather.say(reply)
        gather.pause(length=1)
        response.append(gather)

        return str(response)

    except Exception as e:
        logger.error(f"❌ Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.")
        return str(fallback)

# ✅ Run the app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting Rachel Memory Engine on port {port}")
    app.run(host="0.0.0.0", port=port)
