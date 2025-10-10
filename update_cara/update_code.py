import sounddevice as sd
import requests
import io
import base64
from gtts import gTTS
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents
from fastapi import FastAPI, WebSocket
import tempfile, os
import soundfile as sf
import numpy as np

ai_speaking = False
stop_speaking = False

def text_to_speech(text):
    global ai_speaking, stop_speaking
    ai_speaking = True
    stop_speaking = False

    try:
        tmp_path = tempfile.NamedTemporaryFile(suffix = ".wav", delete = False).name
        tts = gTTS(text)
        tts.save(tmp_path)

        data, fs = sf.read(tmp_path)
        print("Playing AI Repsonse.... (Will stop is user speaks)")
        
        blocksize = 2048
        i = 0
        while i < len(data):
            if stop_speaking:
                print("User started speaking- stopping AI playback.")
                break
            end = min(i+ blocksize, len(data))
            sd.play(data[i:end],fs)
            sd.wait()
            i = end

        sd.stop()
        ai_speaking = False
        os.remove(tmp_path)
    
    except Exception as e:
        print("TTS playback error: ", e)
        ai_speaking = False


def main():
    global ai_speaking, stop_speaking
    
    deepgram = DeepgramClient("6405495cba80ca40af769a18e9d99c6268479c6f")
    dg_connection = deepgram.listen.websocket.v("1")

    def on_message(self, result, **kwargs):
        if not result.is_final:
            return
        sentence = result.channel.alternatives[0].transcript
        if sentence:
            print(f"\nFinal transcript: {sentence}")
            try:
                payload = {"user_id": "janmeet123",
                    "client_id": "44ihRG38UX24DKeFzE15FbbPZfCgz3rh",
                    "text": sentence}
                response = requests.post(url= "https://stgbot.genieus4u.ai/chat/chatbot/", json=payload)
                response.raise_for_status()
                bot_reply = response.json().get("response", "")

                if bot_reply:
                    print(f"Bot reply: {bot_reply}")
                    text_to_speech(bot_reply)
                else:
                    print("No response text from chatbot")
            except Exception as e:
                print("Failed to send transcript: ", e)

        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        options = LiveOptions(
            model= "nova-3-general",
            language="multi",
            encoding="linear16",
            sample_rate=16000,
            interim_results=True,
            endpointing= 2000
        )

        if not dg_connection.start(options):
            print("Failed to connect to Deepgram")
            return

    options = LiveOptions(
        model="nova-3-general",
        language="multi",
        encoding="linear16",   # PCM16 for mic input
        sample_rate=16000,
        interim_results=True,
        endpointing=2000        # ms of silence = end of sentence
    )

    if not dg_connection.start(options):
        print("Failed to connect to Deepgram")
        return

    # Stream mic input
    def callback(indata, frames, time, status):
        global stop_speaking, ai_speaking
        if status:
            print(status)
        
        if ai_speaking:
            amplitude = np.abs(indata).mean()
            if amplitude > 0.02:
                stop_speaking = True
                ai_speaking = False
        dg_connection.send(bytes(indata))

    with sd.RawInputStream(
        samplerate=16000,
        blocksize=8000,
        dtype="int16",
        channels=1,
        device=None,
        callback=callback,
    ):
        input("Speak into your mic. Press Enter to stop...\n")

    # End session
    dg_connection.finish()
    print("✅ Finished")

if __name__ == "__main__":
    main()