from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
import logging
import sys
import time
from memory_engine import MemoryEngine
import requests
from io import BytesIO

# ✅ Config
ELEVENLABS_API_KEY = "sk_bc11b5c020232ad11edfade246e472ffa60993e167ef2075"
ELEVENLABS_VOICE_ID = "MioXIsoKIp7emOKpdXaL"

# ✅ Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ✅ Flask Setup
app = Flask(__name__)
audio_memory_cache = {}

# ✅ ElevenLabs Synthesizer
def synthesize_speech(text):
    if text in audio_memory_cache:
        logger.info(f"✅ Cached audio hit: {text}")
        return text

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

        start = time.time()
        response = requests.post(url, headers=headers, json=payload, stream=True)
        logger.info(f"🕐 TTS time: {time.time() - start:.2f}s")

        if response.status_code == 200:
            audio_data = BytesIO()
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    audio_data.write(chunk)
            audio_data.seek(0)
            if audio_data.getbuffer().nbytes > 0:
                audio_memory_cache[text] = audio_data
                return text
        else:
            logger.error(f"❌ ElevenLabs Error: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"❌ TTS Exception: {e}")
    return None

# ✅ Serve Audio Endpoint
@app.route("/audio/<key>")
def serve_audio(key):
    if key in audio_memory_cache:
        return Response(audio_memory_cache[key].getvalue(), mimetype="audio/mpeg")
    return "Audio not found", 404

# ✅ Memory Engine Init
memory_engine = MemoryEngine(synthesize_fn=synthesize_speech)
silent_attempts = {}

# ✅ /voice – Call Entry Point
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
        gather = Gather(input="speech", timeout=2, speechTimeout="auto", action="/respond_twilio", method="POST")
        if audio_key:
            gather.play(f"/audio/{audio_key}")
        else:
            gather.say(reply)
        response.append(gather)

        return str(response)
    except Exception as e:
        logger.error(f"❌ Error in /voice: {e}")
        fallback = VoiceResponse()
        fallback.say("Sorry, something went wrong.")
        return str(fallback)

# ✅ /respond_twilio – Handle Replies
@app.route("/respond_twilio", methods=["POST"])
def respond_twilio():
    try:
        call_sid = request.form.get("CallSid")
        raw_input = request.form.get("SpeechResult", "")
        user_input = raw_input.strip().lower() if raw_input else ""
        logger.info(f"🗣️ Heard from caller: '{user_input}'")

        response = VoiceResponse()

        # Handle silence
        if not user_input or user_input in ["", ".", "...", "uh", "um", "hmm"]:
            attempts = silent_attempts.get(call_sid, 0) + 1
            silent_attempts[call_sid] = attempts
            msg = "Can you still hear me?" if attempts == 1 else (
                "Just checking back in — are you still there?" if attempts == 2 else
                "Okay, I’ll go ahead and try again another time. Take care!")

            if attempts < 3:
                gather = Gather(input="speech", timeout=2, speechTimeout="auto", action="/respond_twilio", method="POST")
                audio_key = synthesize_speech(msg)
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

        # Reset silence tracker
        silent_attempts[call_sid] = 0

        response_data = memory_engine.generate_response(call_sid, user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")
        reply = reply_text.split("[gather]")[0].strip() if "[gather]" in reply_text else reply_text

        audio_key = synthesize_speech(reply)
        gather = Gather(input="speech", timeout=2, speechTimeout="auto", action="/respond_twilio", method="POST")
        if audio_key:
            gather.play(f"/audio/{audio_key}")
        else:
            gather.say(reply)
        response.append(gather)

        return str(response)
    except Exception as e:
        logger.error(f"❌ Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.")
        return str(fallback)
