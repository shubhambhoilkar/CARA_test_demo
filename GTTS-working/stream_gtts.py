import pygame
import requests, time
import asyncio
import numpy as np
import sounddevice as sd
from gtts import gTTS
from io import BytesIO
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents

async def main():
    deepgram = DeepgramClient("996405495cba80ca40af769a18e9d99")  # Replace with your key
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
                    "user_id": "sam9918",
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
                    # Step 1: Generate audio stream
                    audio_stream = generate_tts_stream(bot_reply)

                    # Step 2: Play it
                    player = AudioPlayer()
                    player.play_audio_stream(audio_stream)

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


class AudioPlayer:
    def __init__(self):
        pygame.mixer.init()
        self.is_playing = False
        self.is_paused = False

    def play_audio_stream(self, audio_stream):
        # Load and play from memory
        pygame.mixer.music.load(audio_stream, 'mp3')
        pygame.mixer.music.play()
        self.is_playing = True
        self.is_paused = False
        print("▶️ Playing streamed audio...")

    def pause(self):
        if self.is_playing and not self.is_paused:
            pygame.mixer.music.pause()
            self.is_paused = True
            print("⏸️ Paused audio")

    def resume(self):
        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            print("▶️ Resumed audio")

    def stop(self):
        pygame.mixer.music.stop()
        self.is_playing = False
        print("⏹️ Stopped audio")

# --- SDK Helper ---
def generate_tts_stream(text: str, lang: str = 'en'):
    """Generate an in-memory audio stream from text."""
    tts = gTTS(text=text, lang=lang, slow=False)
    audio_stream = BytesIO()
    tts.write_to_fp(audio_stream)
    audio_stream.seek(0)
    print("✅ Audio stream ready (no file saved)")
    return audio_stream

asyncio.run(main())
    

