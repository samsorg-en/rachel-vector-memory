# ✅ Twilio Entry Point (Safe with Try-Catch)
@app.route("/voice", methods=["POST"])
def voice():
    try:
        memory_engine.reset_script()  # 🧠 Reset script on new call
        response = VoiceResponse()
        gather = Gather(input="speech", timeout=5, action="/respond_twilio", method="POST")
        gather.say("Hi, this is Rachel from the solar team. Do you have a minute to chat?", voice="Polly.Joanna", language="en-US")
        response.append(gather)
        response.redirect("/voice")  # fallback loop
        return str(response)
    except Exception as e:
        logger.error(f"❌ Error in /voice: {e}")
        fallback = VoiceResponse()
        fallback.say("Sorry, something went wrong with the call. Please try again later.", voice="Polly.Joanna")
        return str(fallback)

# ✅ Handle Twilio Speech Response
@app.route("/respond_twilio", methods=["POST"])
def respond_twilio():
    try:
        user_input = request.form.get("SpeechResult", "")
        logger.info(f"👂 Heard from caller: {user_input}")

        if not user_input:
            logger.info(f"👂 Lane's Debugging 1: {user_input}")
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

        # 🔁 Re-engage with another Gather for next input
        gather = Gather(input="speech", timeout=5, action="/respond_twilio", method="POST")
        gather.say("What else would you like to know about solar?")
        response.append(gather)
        return str(response)

    except Exception as e:
        logger.error(f"❌ Error in /respond_twilio: {e}")
        fallback = VoiceResponse()
        fallback.say("Something went wrong. Please try again later.", voice="Polly.Joanna")
        return str(fallback)
