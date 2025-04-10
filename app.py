from flask import Flask, request, send_file, Response, url_for
from twilio.twiml.voice_response import VoiceResponse, Gather, Pause, Play
import logging
import sys
import os
import time
from memory_engine import MemoryEngine
import requests
from io import BytesIO

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
audio_memory_cache = {}  # Stores {text: BytesIO(audio)} for fast response

# ✅ ElevenLabs Text-to-Speech (Memory-Based)
def synthesize_speech(text):
    if text in audio_memory_cache:
        logger.info(f"✅ In-memory audio found: {text}")
        return text  # Key used to retrieve BytesIO later

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

        response = requests.post(url, headers=headers, json=payload, stream=True)
        if response.status_code == 200:
            audio_data = BytesIO()
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    audio_data.write(chunk)
            audio_data.seek(0)

            if audio_data.getbuffer().nbytes > 0:
                audio_memory_cache[text] = audio_data
                logger.info(f"✅ Audio preloaded into memory: {text}")
                return text
            else:
                logger.error("❌ Audio stream returned empty.")
        else:
            logger.error(f"❌ ElevenLabs Stream Error: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"❌ TTS Stream Exception: {e}")

    return None

# ✅ Serve Audio File (From Memory)
@app.route("/audio/<key>")
def serve_audio(key):
    if key in audio_memory_cache:
        logger.info(f"📤 Serving in-memory audio: {key}")
        return Response(audio_memory_cache[key].getvalue(), mimetype="audio/mpeg")
    logger.warning(f"⚠️ Audio key not found in memory: {key}")
    return "Audio not found", 404

# ✅ Initialize Engine
memory_engine = MemoryEngine(synthesize_fn=synthesize_speech)

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

        audio_key = synthesize_speech(reply)
        gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
        gather.pause(length=1)
        if audio_key:
            gather.play(f"/audio/{audio_key}")
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
                audio_key = synthesize_speech(msg)
                gather.pause(length=1)
                if audio_key:
                    gather.play(f"/audio/{audio_key}")
                else:
                    gather.say(msg)
                response.append(gather)
            else:
                audio_key = synthesize_speech(msg)
                if audio_key:
                    response.play(f"/audio/{audio_key}")
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

        audio_key = synthesize_speech(reply)
        gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
        gather.pause(length=1)
        if audio_key:
            gather.play(f"/audio/{audio_key}")
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
