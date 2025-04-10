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
            next_line = memory_engine.peek_next_line(call_sid, offset=2)
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
            next_line = memory_engine.peek_next_line(call_sid, offset=2)
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
