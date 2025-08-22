import datetime
import os
import threading
from gemini_question_generator import generate_followup_question  # <-- NEW

class InterviewProcessor:
    SILENCE_SECONDS = 10.0

    def __init__(self, tts):
        self.tts = tts
        self.active = True
        self.q = [
            "Tell me about yourself.",
            #"What are your top strengths for this role? Give one example.",
        ]
        self.i = -1
        self.last_question = ""
        self.transcript = []
        self._answer_buf = []
        self._silence_timer = None
        self._lock = threading.Lock()

    def start_interview(self):
        self.active = True
        self.i = -1
        self.transcript.clear()
        self._answer_buf.clear()
        self._cancel_timer()
        self.tts.speak("Hi I am your AI Assistant. I’ll interview you. Say 'skip' to move on, 'repeat' to hear a question again, or 'that's it' after completing your answer.")
        self._ask_next()

    def _ask_next(self):
        with self._lock:
            self._answer_buf.clear()
            self._cancel_timer()

        self.i += 1
        if self.i >= len(self.q):
            self.tts.speak("That’s all I had. Thanks for your time. Would you like quick feedback?")
            self.active = False
            self._save_transcript()
            return "done"

        self.last_question = self.q[self.i]
        self.tts.speak(self.last_question)
        return "ask"

    def _repeat(self):
        if self.last_question:
            self.tts.speak(self.last_question)

    def _skip(self):
        return self._ask_next()

    def _ack(self, low_text: str) -> str:
        if any(k in low_text for k in ["xgboost", "rag", "langchain", "aws", "terraform", "timeseries", "arima", "llm"]):
            return "Got it. Thanks. "
        if any(k in low_text for k in ["team", "stakeholder", "client", "collaborat"]):
            return "Understood. "
        return "Thanks. "

    def _save_transcript(self):
        if not self.transcript:
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"interview_transcript_{ts}.txt"
        try:
            with open(fname, "w", encoding="utf-8") as f:
                for qi, (q, a) in enumerate(self.transcript, 1):
                    f.write(f"Q{qi}: {q}\n")
                    f.write(f"A{qi}: {a}\n\n")
            print(f"[TRANSCRIPT] Saved to {os.path.abspath(fname)}")
        except Exception as e:
            print(f"[TRANSCRIPT ERROR] {e}")

    def _cancel_timer(self):
        if self._silence_timer is not None:
            try:
                self._silence_timer.cancel()
            except Exception:
                pass
            self._silence_timer = None

    def _schedule_finalize(self):
        self._cancel_timer()
        self._silence_timer = threading.Timer(self.SILENCE_SECONDS, self._finalize_answer_if_any)
        self._silence_timer.daemon = True
        self._silence_timer.start()

    def _finalize_answer_if_any(self):
        with self._lock:
            answer = " ".join(self._answer_buf).strip()
            self._answer_buf.clear()
        if not answer:
            self.tts.speak("If you’re ready, please answer now or say skip.")
            return

        if 0 <= self.i < len(self.q):
            q = self.q[self.i]
            self.transcript.append((q, answer))

            low = answer.lower()
            followup = ""

            if "strength" in q.lower() and len(answer.split()) < 15:
                followup = " Please add one concrete example with measurable impact."
            if "challenging problem" in q.lower() and ("impact" not in low and "result" not in low):
                followup += " Also cover the impact or result in one line."

            # 🔁 Gemini-based question generation
            new_q = generate_followup_question(answer)
            if new_q and new_q not in self.q:
                self.q.append(new_q)

            if self.i + 1 >= len(self.q):
                self.tts.speak(self._ack(low) + "That’s all I had. We’ll review your answers and our HR will contact you soon.", block=True)
                self.active = False
                self._save_transcript()
                os._exit(0)
            else:
                self.tts.speak(self._ack(low) + "Next question." + followup)
                self._ask_next()

    def process_input(self, text: str):
        if not self.active:
            return

        low = text.lower().strip()

        if any(k in low for k in ["stop interview", "end interview", "exit", "quit"]):
            self.tts.speak("Ending the interview session. Thank you for your time!", block=True)
            self.active = False
            self._cancel_timer()
            self._finalize_answer_if_any()
            self._save_transcript()
            return "exit"

        if "repeat" in low:
            self._repeat()
            return "repeat"

        if "skip" in low:
            with self._lock:
                self._answer_buf.clear()
            return self._skip()

        with self._lock:
            self._answer_buf.append(text)

        end_keywords = ["that's it", "i'm done", "that is all", "i'm finished", "that's all"]
        if any(k in low for k in end_keywords):
            self._cancel_timer()
            self._finalize_answer_if_any()
            return "finalized"

        self._schedule_finalize()
        return "collecting"
