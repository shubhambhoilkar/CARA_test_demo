import streamlit as st
import requests
import subprocess
import threading

st.set_page_config(page_title= "Voice Chat Demo", page_icon= "🎤", layout="centered")

st.title("🎤 Voice Chatbot Demo")
st.write("Speak into Your microphone, get live transcription & chatbot responses.")

def run_backend():
    subprocess.run(["Python", "deepgram_transcription.py"])

if st.button("▶️ Start Voice Chat"):
    st.write("Listening.... Speak now!")
    threading.Thread(target=run_backend).start()

st.subheader("💬 Chatbot Interaction")
user_text = st.text_input("Or type your message here:")
if st.button("send"):
    payload = {
        "user_id":"sam9918",
        "client_id": "44ihRG38UX24DKeFzE15FbbPZfCgz3rh",
        "text": user_text
    }
    response = requests.post("https://stgbot.genieus4u.ai/chat/chatbot/", json= payload)
    if response.ok:
        st.success(response.json().get("response"))
    else:
        st.error("API Error: "+ str(response.text))