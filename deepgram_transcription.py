#Janmeet code reference
import sounddevice as sd
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents

def main():
    deepgram = DeepgramClient("Deepgram_api_key_here")
    dg_connection = deepgram.listen.websocket.v("1")
    
    try:
        def on_message(self, result, **kwargs):
            if not result.is_final:
                return
            sentence = result.channel.alternatives[0].transcript
            if sentence:
                print(f"Final transcript: {sentence}")

        dg_connection.on(LiveTranscriptionEvents.Transcript,on_message)

        options = LiveOptions(
            model= "nova-3-general",
            language= "multi",
            encoding= "linear16", # PCM16 for Mic Input
            sample_rate= 16000,
            interim_results= True,
            endpointing= 2000
        )

        if not dg_connection.start(options):
            print("Failed to connect to Deepgram")
            return
        
        # Stream min input
        def callback(indata, frame, time, status):
            if status:
                print(status)
            dg_connection.send(bytes(indata))

        with sd.RawInputStream(
            samplerate = 16000,
            blocksize = 8000,
            dtype = "int16",
            channels = 1,
            device =None,
            callback= callback):
            input("Speak into you mic. Press Enter to Stop!:\n")

        #End Session
        dg_connection.finish()
        print("Transcription Complete")

    except Exception as e:
        return (f"Transcription Failed, check error: {e}")

if __name__ == "__main__":
    main()