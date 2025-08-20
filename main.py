from whisper_transcriber import WhisperTranscriber
from text_to_speech import TextToSpeech
from interview_processor import InterviewProcessor
import time

class AIInterviewAssistant:
    def __init__(self):
        self.tts = TextToSpeech()
        self.processor = InterviewProcessor(self.tts)
        self.stt = WhisperTranscriber(on_text=self.process_user_input)

        # Pause mic during AI speech
        self.tts.on_start = getattr(self.stt, "pause", None)
        self.tts.on_end = getattr(self.stt, "resume", None)

        self.running = True

    def process_user_input(self, text):
        print(f"User: {text}")                 # Only 'User:' lines
        result = self.processor.process_input(text)
        if result == "exit":
            self.stop()

    def start(self):
        # Start interview immediately
        self.processor.start_interview()
        self.stt.start()
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        self.stt.stop()
        print("\nSession ended. Goodbye!")

if __name__ == "__main__":
    assistant = AIInterviewAssistant()
    assistant.start()

