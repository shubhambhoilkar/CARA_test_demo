import io
import os
import base64
import tempfile
import requests
import soundfile as sf
import sounddevice as sd
from gtts import gTTS
from fastapi import FastAPI, WebSocket
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents

def main():
    deepgram = DeepgramClient("6405495cba80ca40af769a18e9d99c6268479c6f")
    dg_connection = deepgram.listen.websocket.v("1")

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
                    text_to_speech(bot_reply)
                else:
                    print("⚠ No response text from chatbot")

            except Exception as e:
                print("❌ Failed to send transcript: ", e)

    def text_to_speech(text):
        """Convert text to speech and play it."""
        try:
            tmp_path= tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
            tts = gTTS(text)
            tts.save(tmp_path)

            data, fs = sf.read(tmp_path)
            print("Playing response.")
            sd.play(data, fs)
            sd.wait()

            os.remove(tmp_path)
        except Exception as e:
            print("❌ TTS playback error:", e)

    # Register Deepgram event handler
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

    # Deepgram configuration
    options = LiveOptions(
        model="nova-3-general",
        language="multi",
        encoding="linear16",  # PCM16 mic input
        sample_rate=16000,
        interim_results=True,
        endpointing=2000
    )

    if not dg_connection.start(options):
        print("Failed to connect to Deepgram")
        return

    # Stream mic input continuously
    def callback(indata, frames, time, status):
        if status:
            print(status)
        dg_connection.send(bytes(indata))

    with sd.RawInputStream(
        samplerate=16000,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=callback
    ):
        input("🎤 Speak into your mic. Press Enter to stop...\n")

    # End session
    dg_connection.finish()
    print("✅ Session finished")

if __name__ == "__main__":
    main()
