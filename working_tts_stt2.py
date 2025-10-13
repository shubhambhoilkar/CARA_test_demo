import os
import requests
import sounddevice as sd
import threading
import time
import asyncio
import logging
from dotenv import load_dotenv
from elevenlabs.play import play
from elevenlabs.client import ElevenLabs
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pygame
import numpy as np

# --- Silence noisy websocket logs ---
logging.getLogger("websockets").setLevel(logging.ERROR)

# --- Optional: make Deepgram more responsive to ping loss ---
os.environ["DEEPGRAM_WS_PING_INTERVAL"] = "15"

load_dotenv()

# Initialize ElevenLabs
elevenlabs = ElevenLabs(
    api_key="sk_649176a657f8fd901eac9")

def eleven_labs_audio(sentence, control_flags):
    """Play ElevenLabs TTS audio in a background thread (non-blocking)."""
    def _play_audio():
        try:
            audio = elevenlabs.text_to_speech.convert(
                text=sentence,
                voice_id="JBFqnCBsd6RMkjVDRZzb",
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128"
            )
            audio_bytes = b"".join(audio)
            temp_file = "temp_ai_file.mp3"
            with open(temp_file, "wb") as f:
                f.write(audio_bytes)

            pygame.mixer.init()
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            print("AI Speaking....")

            while pygame.mixer.music.get_busy():
                if control_flags["user_is_speaking"]:
                    if not control_flags["ai_paused"]:
                        pygame.mixer.music.pause()
                        control_flags["ai_paused"]= True
                        print("AI Paused --Customer Speaking")
                    else:
                        if control_flags["ai_paused"]:
                            pygame.mixer.music.unpause()
                            control_flags["ai_Paused"] = False
                            print("AI Resumed")
                    time.sleep(0.1)
                pygame.mixer.music.stop()
                pygame.mixer.quit()
                print("AI Finished Speaking.")

        except Exception as e:
            print("❌ ElevenLabs TTS error:", e)

    # Run playback asynchronously so it doesn’t block Deepgram stream
    threading.Thread(target=_play_audio, daemon=True).start()

async def main():
    deepgram = DeepgramClient("6405495cba80ca40af769a18e9d99")
    dg_connection = deepgram.listen.websocket.v("1")

    # --- Config ---
    options = LiveOptions(
        model="nova-3-general",
        language="multi",
        encoding="linear16",  # PCM16 mic input
        sample_rate=16000,
        interim_results=True,
        endpointing=2000
    )

    last_ping = time.time()  # For keepalive heartbeat
    control_flags = {
        "user_is_speaking": False,
        "ai_paused": False,
        "last_user_activity": time.time(),
        "ai_can_speak": False
    }

    # --- Event handler for Deepgram messages ---
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
                if bot_reply:
                    print(f"🤖 Bot reply: {bot_reply}")
#                    eleven_labs_audio(bot_reply)
                    def delayed_speech():
                        while time.time() - control_flags["last_user_activity"] < 1:
                            time.sleep(0.1)
                        if not control_flags["user_is_speaking"]:
                            eleven_labs_audio(bot_reply, control_flags)

                    threading.Thread(target=delayed_speech, daemon=True).start()

                else:
                    print("⚠ No response text from chatbot")

            except Exception as e:
                print("❌ Failed to send transcript:", e)

    # Register event handler
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

    # --- Start Deepgram stream ---
    connected = dg_connection.start(options)
    if not connected:
        print("❌ Failed to connect to Deepgram")
        return

    print("✅ Connected to Deepgram live transcription")

    # --- Mic input stream callback ---
    def callback(indata, frames, time_info, status):
        nonlocal last_ping
        volume_norm = np.linalg.norm(indata) * 10
        if volume_norm > 50:  # Simple voice activity detection threshold
            control_flags["user_is_speaking"] = True
            control_flags["last_user_activity"] = time.time()
        else:
            # If silence for >0.5s, mark user as not speaking
            if time.time() - control_flags["last_user_activity"] > 0.5:
                control_flags["user_is_speaking"] = False

        if status:
            print("⚠️ Audio status:", status)

        try:
            dg_connection.send(bytes(indata))

            # Send heartbeat ping every ~25 seconds
            if time.time() - last_ping > 25:
                dg_connection.send(b" ")  # keepalive ping
                last_ping = time.time()

        except Exception as e:
            err = str(e)
            if "ConnectionClosed" in err or "ping timeout" in err:
                print("🔁 Deepgram connection lost — reconnecting...")
                try:
                    dg_connection.finish()
                    time.sleep(2)
                    if dg_connection.start(options):
                        last_ping = time.time()
                        print("✅ Reconnected to Deepgram.")
                    else:
                        print("❌ Reconnect failed to Deepgram.")
                except Exception as inner:
                    print("❌ Reconnect exception:", inner)
            else:
                print("⚠️ send() failed:", e)

    # --- Start mic stream ---
    with sd.RawInputStream(
        samplerate=16000,
        blocksize=32000,  # ⬆️ Increased buffer size
        dtype="int16",
        channels=1,
        callback=callback
    ):
        input("🎤 Speak into your mic. Press Enter to stop...\n")

    # --- Clean up ---
    dg_connection.finish()
    print("✅ Session finished")

if __name__ == "__main__":
    asyncio.run(main())
