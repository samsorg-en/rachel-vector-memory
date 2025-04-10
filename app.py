from flask import Flask, request, send_file, Response
from twilio.twiml.voice_response import VoiceResponse, Gather, Pause
import logging
import sys
import os
from memory_engine import MemoryEngine
from urllib.parse import quote_plus
import io
import requests
import threading

# ✅ Logging Setup
logging.basicConfig(
    level="INFO",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ✅ Flask App Setup
app = Flask(__name__)
memory_engine = MemoryEngine()

# ✅ Silence Tracker
silent_attempts = {}

# ✅ In-memory audio cache
audio_cache = {}

def precache_audio(text):
    if text in audio_cache:
        return
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL/stream"
        headers = {
            "xi-api-key": "sk_bc11b5c020232ad11edfade246e472ffa60993e167ef2075",
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
        audio_cache[text] = b"".join(response.iter_content(chunk_size=2048))
        logger.info(f"🔊 Preloaded audio for: {text}")
    except Exception as e:
        logger.error(f"❌ Preload failed for: {text} — {e}")

# ✅ Preload top 3 script lines at startup
try:
    preload_lines = memory_engine.get_initial_script_lines(3)
    for line in preload_lines:
        threading.Thread(target=precache_audio, args=(line,)).start()
except Exception as e:
    logger.error(f"❌ Failed to preload initial lines: {e}")

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

        # ✅ Pre-cache next line in background
        def precache_next_line():
            next_line = memory_engine.peek_next_line(call_sid)
            if next_line:
                precache_audio(next_line)
                logger.info(f"🔊 Pre-cached next line for {call_sid}")

        threading.Thread(target=precache_next_line).start()

        gather = Gather(
            input="speech",
            timeout=3,
            speechTimeout="auto",
            action="/respond_twilio",
            method="POST"
        )
        gather.pause(length=1)
        gather.play(f"https://rachel-vector-memory.fly.dev/speech?text={url_encoded_text}")
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

        logger.info(f"👃 Heard from caller: '{user_input}'")
        response = VoiceResponse()

        if not user_input or user_input in ["", ".", "...", "uh", "um", "hmm"]:
            attempts = silent_attempts.get(call_sid, 0) + 1
            silent_attempts[call_sid] = attempts
            logger.info(f"🨫 Silence attempt #{attempts}")

            if attempts == 1:
                gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
                gather.play("https://rachel-vector-memory.fly.dev/speech?text=Can+you+still+hear+me%3F")
                response.append(gather)
                return str(response)

            elif attempts == 2:
                gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
                gather.play("https://rachel-vector-memory.fly.dev/speech?text=Just+checking+back+in+%E2%80%94+are+you+still+there%3F")
                response.append(gather)
                return str(response)

            else:
                response.say("Okay, I’ll go ahead and try again another time. Take care!", voice="Polly.Joanna")
                response.hangup()
                silent_attempts.pop(call_sid, None)
                memory_engine.reset_script(call_sid)
                return str(response)

        silent_attempts[call_sid] = 0
        response_data = memory_engine.generate_response(call_sid, user_input)
        reply_text = response_data.get("response", "I'm not sure how to respond to that.")
        logger.info(f"🗣️ Rachel: {reply_text}")

        reply = reply_text.split("[gather]")[0].strip() if "[gather]" in reply_text else reply_text
        url_encoded_text = quote_plus(reply)

        def precache_next_line():
            next_line = memory_engine.peek_next_line(call_sid)
            if next_line:
                precache_audio(next_line)
                logger.info(f"🔊 Pre-cached next line for {call_sid}")

        threading.Thread(target=precache_next_line).start()

        gather = Gather(input="speech", timeout=3, speechTimeout="auto", action="/respond_twilio", method="POST")
        gather.pause(length=1)
        gather.play(f"https://rachel-vector-memory.fly.dev/speech?text={url_encoded_text}")
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
    if text in audio_cache:
        return Response(
            io.BytesIO(audio_cache[text]),
            mimetype="audio/mpeg",
            headers={
                "Transfer-Encoding": "chunked",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )

    voice_id = "EXAVITQu4vr4xnSDxMaL"
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

    def generate():
        for chunk in response.iter_content(chunk_size=2048):
            if chunk:
                yield chunk

    return Response(
        generate(),
        mimetype="audio/mpeg",
        headers={
            "Transfer-Encoding": "chunked",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

# ✅ Run the app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting Rachel Memory Engine on port {port}")
    app.run(host="0.0.0.0", port=port)
