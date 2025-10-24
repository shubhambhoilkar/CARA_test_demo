import os
import requests
import sounddevice as sd
import threading
import time
import asyncio
import logging
import numpy as np
from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from elevenlabs.play import play
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents

# --- Setup ---
logging.getLogger("websockets").setLevel(logging.ERROR)
os.environ["DEEPGRAM_WS_PING_INTERVAL"] = "15"
load_dotenv()

# Initialize ElevenLabs
elevenlabs = ElevenLabs(api_key="sk_2022fa3cb0630c5509ea9")  # Replace with your key

def eleven_labs_audio(sentence, control_flags):
    """Play ElevenLabs TTS audio asynchronously with pause/resume logic."""
    def _play_audio():
        try:
            print("🧠 Generating AI speech...")
            audio = elevenlabs.text_to_speech.convert(
                text=sentence,
                voice_id="JBFqnCBsd6RMkjVDRZzb",  # Use your preferred voice ID
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128"
            )
            print("🔊 AI Speaking...")
            return play(audio)

            # print("✅ AI Finished Speaking.")

        except Exception as e:
            print("❌ ElevenLabs TTS error:", e)

    threading.Thread(target=_play_audio, daemon=True).start()


# --- MAIN PROGRAM ---
async def main():
    deepgram = DeepgramClient("6405495cba80ca40af769a18e9d99")  # Replace with your key
    dg_connection = deepgram.listen.websocket.v("1")

    options = LiveOptions(
        model="nova-3-general",
        language="multi",
        encoding="linear16",
        sample_rate=16000,
        interim_results=True,
        endpointing=2000
    )

    last_ping = time.time()
    control_flags = {
        "user_is_speaking": False,
        "ai_paused": False,
        "last_user_activity": time.time(),
    }

    # --- Deepgram Event Handler ---
    def on_message(self, result, **kwargs):
        if not result.is_final:
            return

        sentence = result.channel.alternatives[0].transcript
        if sentence:
            print(f"\n🎙 Final transcript: {sentence}")

            try:
                payload = {
                    "user_id": "janmeet123",
                    "client_id": "44ihRG38UX24DKeFzE15FbbPZfCgz3rh",
                    "text": sentence
                }

                response = requests.post(
                    url="https://stgbot.genieus4u.ai/chat/chatbot/",
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()

                bot_reply = response.json().get("response", "")
                print(f"AI Response: {bot_reply}")
                if bot_reply:
                    eleven_labs_audio(bot_reply, control_flags)
                #     print(f"🤖 Bot reply: {bot_reply}")

                #     # Wait until user is silent for 1s before AI speaks
                #     def delayed_speech():
                #         while time.time() - control_flags["last_user_activity"] < 1:
                #             time.sleep(0.1)
                #         if not control_flags["user_is_speaking"]:
                #             eleven_labs_audio(bot_reply, control_flags)

                #     threading.Thread(target=delayed_speech, daemon=True).start()
                # else:
                #     print("⚠ No response text from chatbot")

            except Exception as e:
                print("❌ Failed to send transcript:", e)

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

    if not dg_connection.start(options):
        print("❌ Failed to connect to Deepgram")
        return

    print("✅ Connected to Deepgram and listening...")

    # --- Microphone Callback ---
    def callback(indata, frames, time_info, status):
        nonlocal last_ping
        volume_norm = np.linalg.norm(indata) * 10
        if volume_norm > 50:  # Simple speech detection
            control_flags["user_is_speaking"] = True
            control_flags["last_user_activity"] = time.time()
        else:
            if time.time() - control_flags["last_user_activity"] > 0.5:
                control_flags["user_is_speaking"] = False

        if status:
            print("⚠️ Audio status:", status)

        try:
            dg_connection.send(bytes(indata))

            # Heartbeat ping
            if time.time() - last_ping > 25:
                dg_connection.send(b" ")
                last_ping = time.time()

        except Exception as e:
            err = str(e)
            if "ConnectionClosed" in err or "ping timeout" in err:
                print("🔁 Reconnecting to Deepgram...")
                try:
                    dg_connection.finish()
                    time.sleep(2)
                    if dg_connection.start(options):
                        last_ping = time.time()
                        print("✅ Reconnected to Deepgram.")
                    else:
                        print("❌ Reconnect failed.")
                except Exception as inner:
                    print("❌ Deepgram reconnect error:", inner)
            else:
                print("⚠️ send() failed:", e)

    # --- Start Listening ---
    with sd.RawInputStream(
        samplerate=16000,
        blocksize=32000,
        dtype="int16",
        channels=1,
        callback=callback
    ):
        input("🎤 Speak into your mic. Press Enter to stop...\n")

    dg_connection.finish()
    print("✅ Session finished")


if __name__ == "__main__":
    asyncio.run(main())
