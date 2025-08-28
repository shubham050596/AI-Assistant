# main.py
import argparse
import time
from whisper_transcriber import WhisperTranscriber
from text_to_speech import TextToSpeech
from interview_processor import InterviewProcessor

class AIInterviewAssistant:
    def __init__(self, resume_path: str = "", jd_path: str = ""):
        self.tts = TextToSpeech()
        self.processor = InterviewProcessor(self.tts)

        # Load resume & job description if provided
        if resume_path:
            self.processor.load_resume(resume_path)
        if jd_path:
            self.processor.load_job_description(jd_path)

        # Speech-to-text
        self.stt = WhisperTranscriber(on_text=self.process_user_input)

        # Pause mic when AI is speaking
        self.tts.on_start = getattr(self.stt, "pause", None)
        self.tts.on_end = getattr(self.stt, "resume", None)

        self.running = True

    def process_user_input(self, text):
        print(f"User: {text}")
        result = self.processor.process_input(text)
        if result == "exit":
            self.stop()

    def start(self):
        # Start the interview immediately
        self.processor.start_interview()
        self.stt.start()

        try:
            while self.running:
                # 👇 Auto-stop when interview is finished (processor is inactive)
                if not self.processor.active:
                    self.stop()
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False

        try:
            self.stt.stop()
        except Exception:
            pass

        try:
            # Ensure everything is finalized
            self.processor._cancel_timer()
            self.processor._finalize_answer_if_any()
            self.processor._save_transcript()
        except Exception:
            pass

        print("\nSession ended. Goodbye!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", default="", help="Path to candidate resume (.txt/.pdf/.docx)")
    parser.add_argument("--jd", default="", help="Path to job description (.txt/.pdf/.docx)")
    args = parser.parse_args()

    assistant = AIInterviewAssistant(resume_path=args.resume, jd_path=args.jd)
    assistant.start()
