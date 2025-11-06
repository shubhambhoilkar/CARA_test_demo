import os
import io
import base64
import asyncio
import requests
import threading
import time
import numpy as np
# import faiss
from gtts import gTTS
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
# from motor.motor_asyncio import AsyncIOMotorClient
# from sentence_transformers import SentenceTransformer
# from typing import List
from dotenv import load_dotenv
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
    Microphone,
)
import uvicorn

# =========================================
# ENV + DB CONFIG
# =========================================
load_dotenv()
# DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_API_KEY = "996405495cba80ca40af769a18e9d99c6268479c6f"
# MONGO_URI = os.getenv("MONGO_URI")

if not DEEPGRAM_API_KEY:
    raise EnvironmentError("Missing DEEPGRAM_API_KEY in .env")

# client = AsyncIOMotorClient(MONGO_URI)
# db = client["Central_Hospital"]
# collection = db["central_hospital_ai_chunks"]
# model = SentenceTransformer("all-MiniLM-L6-v2")

# =========================================
# FASTAPI + GLOBAL STATE
# =========================================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ai_is_speaking = False
user_interrupt = False
playback_thread = None


# =========================================
# HELPER FUNCTIONS
# =========================================
# def load_and_chunk(file_path: str, chunk_size: int = 500) -> List[str]:
#     with open(file_path, "r", encoding="utf-8") as f:
#         text = f.read()
#     return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


# async def store_prompt_in_mongo(file_path: str):
#     existing = await collection.count_documents({})
#     if existing > 0:
#         return
#     print("📝 Storing prompt chunks into MongoDB...")
#     chunks = load_and_chunk(file_path)
#     for i, chunk in enumerate(chunks):
#         embedding = model.encode(chunk).tolist()
#         await collection.insert_one({
#             "chunk_id": i,
#             "text": chunk,
#             "embedding": embedding
#         })


# async def load_chunks_from_mongo():
#     cursor = collection.find().sort("chunk_id", 1)
#     docs = await cursor.to_list(length=None)
#     if not docs:
#         raise Exception("Chunks not found.")
#     texts = [doc["text"] for doc in docs]
#     embeddings = np.array([doc["embedding"] for doc in docs], dtype="float32")
#     index = faiss.IndexFlatL2(embeddings.shape[1])
#     index.add(embeddings)
#     return texts, index


# @app.on_event("startup")
# async def startup_event():
#     global chunk_texts, faiss_index
#     await store_prompt_in_mongo("ONLY_CENTRAL_HOSPITAL_KB.TXT")
#     chunk_texts, faiss_index = await load_chunks_from_mongo()
#     print("✅ FAISS and Mongo loaded.")


# =========================================
# LLM INTEGRATION (Genieus Endpoint)
# =========================================
async def get_ai_response(prompt: str):
    """Get response from Genieus AI model."""
    try:
        payload = {
            "user_id": "sam9918",
            "client_id": "44ihRG38UX24DKeFzE15FbbPZfCgz3rh",
            "text": prompt
        }

        response = requests.post(
            url="https://stgbot.genieus4u.ai/chat/chatbot/",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        bot_reply = response.json().get("response", "")
        print(f"🤖 AI Response: {bot_reply}")
        return bot_reply

    except Exception as e:
        print(f"❌ LLM Error: {e}")
        return "Sorry, I couldn’t process that right now."


# =========================================
# TEXT TO SPEECH (INTERRUPTIBLE)
# =========================================
async def text_to_speech_with_interrupt(text: str, websocket: WebSocket):
    """
    Convert AI text to speech and allow interruption
    when user starts speaking again.
    """
    global ai_is_speaking, user_interrupt, playback_thread

    # Generate TTS audio
    tts = gTTS(text)
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    audio_base64 = base64.b64encode(audio_buffer.read()).decode("utf-8")

    # Send base64 audio and text to client
    await websocket.send_json({
        "text": text,
        "audio": audio_base64
    })

    ai_is_speaking = True
    user_interrupt = False

    # Simulate playback duration to handle interruptions
    def playback_simulation():
        global ai_is_speaking
        print("🎧 AI speaking...")
        duration = max(2, len(text) / 18)
        start = time.time()
        while time.time() - start < duration:
            if user_interrupt:
                print("⏸️ AI playback interrupted.")
                ai_is_speaking = False
                return
            time.sleep(0.2)
        ai_is_speaking = False
        print("✅ AI finished speaking.")

    playback_thread = threading.Thread(target=playback_simulation, daemon=True)
    playback_thread.start()


# =========================================
# DEEPGRAM SPEECH-TO-TEXT STREAMING
# =========================================
async def get_transcript(websocket: WebSocket):
    """Listens to user mic in real-time using Deepgram."""
    global user_interrupt
    try:
        config = DeepgramClientOptions(options={"keepalive": "true"})
        deepgram = DeepgramClient(DEEPGRAM_API_KEY, config)
        dg_connection = deepgram.listen.asyncwebsocket.v("1")

        async def on_message(self, result, **kwargs):
            global user_interrupt
            if not result.speech_final:
                return

            sentence = result.channel.alternatives[0].transcript.strip()
            if sentence:
                print(f"🎙️ User: {sentence}")
                user_interrupt = True  # Interrupt AI playback if ongoing
                ai_response = await get_ai_response(sentence)
                await text_to_speech_with_interrupt(ai_response, websocket)

        async def on_error(self, error, **kwargs):
            print(f"Deepgram error: {error}")

        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)

        options = LiveOptions(
            model="nova-2",
            punctuate=True,
            language="en-US",
            encoding="linear16",
            sample_rate=16000,
            channels=1,
        )

        await dg_connection.start(options)
        microphone = Microphone(dg_connection.send)
        microphone.start()

        while microphone.is_active():
            await asyncio.sleep(1)

        microphone.finish()
        await dg_connection.finish()

    except Exception as e:
        print(f"❌ Deepgram Error: {e}")


# =========================================
# MAIN WEBSOCKET ENDPOINT
# =========================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global ai_is_speaking, user_interrupt
    await websocket.accept()
    print("✅ WebSocket connected")

    try:
        while True:
            user_message = await websocket.receive_text()
            print(f"🗣️ User said: {user_message}")

            # Handle interruption
            if ai_is_speaking:
                user_interrupt = True
                await websocket.send_json({"pause": True})
                print("🛑 Interrupt detected, pausing AI.")

            ai_response = await get_ai_response(user_message)
            await text_to_speech_with_interrupt(ai_response, websocket)

    except Exception as e:
        print(f"⚠️ WebSocket closed: {e}")
    finally:
        await websocket.close()
        print("🔌 WebSocket disconnected.")


# =========================================
# ENTRY POINT
# =========================================
if __name__ == "__main__":
    uvicorn.run("sam_voice_bot_update:app", host="0.0.0.0", port=9900, reload=True)
