import datetime
import os
import threading

from file_loaders import load_text
from gemini_question_generator import (
    generate_seed_questions,
    generate_followup_question,
    generate_score_and_feedback,
)

class InterviewProcessor:
    SILENCE_SECONDS = 10.0

    def __init__(self, tts):
        self.tts = tts
        self.active = True
        self.resume_text = ""
        self.jd_text = ""
        self.q = ["Tell me about yourself."]
        self.i = -1
        self.last_question = ""
        self.transcript = []
        self._answer_buf = []
        self._silence_timer = None
        self._lock = threading.Lock()
        self.max_questions = 3
        self.on_complete = None  # optional callback (GUI/CLI can set)
        self.last_result = None  # holds scorecard

    # ----------------- file loaders -----------------
    def load_resume(self, path: str):
        self.resume_text = (load_text(path) or "").strip()

    def load_job_description(self, path: str):
        self.jd_text = (load_text(path) or "").strip()

    # ----------------- lifecycle -----------------
    def start_interview(self):
        self.active = True
        self.i = -1
        self.transcript.clear()
        self._answer_buf.clear()
        self._cancel_timer()

        # Seed tailored questions after opener
        if self.jd_text or self.resume_text:
            seeds = generate_seed_questions(
                self.resume_text, self.jd_text, n=min(2, self.max_questions)
            )
            self.q = ["Tell me about yourself."] + [s for s in seeds if s]
            self.q = self.q[:self.max_questions]

        self.tts.speak(
            "Hi I am your AI Assistant. I’ll interview you. Say 'skip' to move on, 'repeat' to hear a question again, or 'that's it' after completing your answer."
        )
        self._ask_next()

    def _ask_next(self):
        with self._lock:
            self._answer_buf.clear()
            self._cancel_timer()
            self.i += 1
            if self.i >= self.max_questions or self.i >= len(self.q):
                self.tts.speak("That’s all I had. Thanks for your time. Would you like quick feedback?")
                self._complete()
                return "done"
            self.last_question = self.q[self.i]

        self.tts.speak(self.last_question)
        if self.active:
            self._schedule_finalize()
        return "ask"

    # ----------------- helpers -----------------
    def _ack(self, low_text: str) -> str:
        TECH = {"xgboost", "rag", "langchain", "aws", "terraform", "timeseries", "arima", "llm"}
        PEOPLE = {"team", "stakeholder", "client", "collaborat"}
        if any(k in low_text for k in TECH): return "Got it. Thanks. "
        if any(k in low_text for k in PEOPLE): return "Understood. "
        return "Thanks. "

    def _save_transcript(self):
        if not self.transcript:
            return
        os.makedirs("transcripts", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        txt = os.path.join("transcripts", f"interview_{ts}.txt")
        try:
            with open(txt, "w", encoding="utf-8") as f:
                for qi, (q, a) in enumerate(self.transcript, 1):
                    f.write(f"Q{qi}: {q}\n")
                    f.write(f"A{qi}: {a}\n\n")
            print(f"[TRANSCRIPT] Saved to {os.path.abspath(txt)}")
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
        if not self.active:
            return
        self._cancel_timer()
        t = threading.Timer(self.SILENCE_SECONDS, self._finalize_answer_if_any)
        t.daemon = True
        t.start()
        self._silence_timer = t

    def _complete(self):
        # mark finished, stop timers
        self.active = False
        self._cancel_timer()

        # Save base transcript first
        self._save_transcript()

        # Score & feedback
        try:
            result = generate_score_and_feedback(
                self.resume_text, self.jd_text, self.transcript, pass_threshold=60
            )
            self.last_result = result
            score = result.get("score", 0)
            verdict = result.get("verdict", "Reject")
            reasons = result.get("reasons", [])
            suggestions = result.get("suggestions", [])

            # Speak short summary
            self.tts.speak(f"Overall score {score} out of 100. Verdict: {verdict}.", block=True)

            # Append summary and write JSON sidecar
            try:
                os.makedirs("transcripts", exist_ok=True)
                txts = [os.path.join("transcripts", f) for f in os.listdir("transcripts") if f.endswith(".txt")]
                latest_txt = max(txts, key=os.path.getmtime) if txts else None

                if latest_txt:
                    with open(latest_txt, "a", encoding="utf-8") as f:
                        f.write(f"---\nSCORE: {score}/100\nVERDICT: {verdict}\n")
                        if reasons:
                            f.write("REASONS:\n")
                            for r in reasons[:3]:
                                f.write(f"- {r}\n")
                        if suggestions:
                            f.write("SUGGESTIONS:\n")
                            for s in suggestions[:3]:
                                f.write(f"- {s}\n")

                    import json, pathlib
                    json_path = pathlib.Path(latest_txt).with_suffix(".json")
                    payload = {
                        "questions": [{"q": q, "a": a} for (q, a) in self.transcript],
                        "scorecard": result,
                    }
                    with open(json_path, "w", encoding="utf-8") as jf:
                        json.dump(payload, jf, ensure_ascii=False, indent=2)
                    print(f"[SCORECARD] {score}/100 ({verdict}) -> {json_path}")
            except Exception as e:
                print(f"[Score Persist Error] {e}")

        except Exception as e:
            print(f"[Scoring Error] {e}")

        # Notify GUI/CLI
        if self.on_complete:
            try:
                self.on_complete()
            except Exception:
                pass

    # ----------------- finalize -----------------
    def _finalize_answer_if_any(self):
        if not self.active:
            return

        with self._lock:
            answer = " ".join(self._answer_buf).strip()
            self._answer_buf.clear()

        if not answer:
            if not self.active:
                return
            self.tts.speak("If you’re ready, please answer now or say skip.")
            return

        with self._lock:
            q = self.q[self.i] if 0 <= self.i < len(self.q) else ""

        low = answer.lower()
        followup = ""
        if "strength" in q.lower() and len(answer.split()) < 15:
            followup = " Please add one concrete example with measurable impact."
        if "challenging problem" in q.lower() and ("impact" not in low and "result" not in low):
            followup += " Also cover the impact or result in one line."

        new_q = generate_followup_question(answer)

        with self._lock:
            self.transcript.append((q, answer))
            if new_q and new_q not in self.q and len(self.q) < self.max_questions:
                self.q.append(new_q)
            done = (self.i + 1) >= self.max_questions

        if done:
            self.tts.speak(
                self._ack(low) + "That’s all I had. We’ll review your answers and our HR will contact you soon.",
                block=True
            )
            self._complete()
            return

        self.tts.speak(self._ack(low) + "Next question." + followup)
        self._ask_next()

    # ----------------- input -----------------
    def process_input(self, text: str):
        if not self.active:
            return

        low = text.lower().strip()

        if any(k in low for k in ["stop interview", "end interview", "exit", "quit"]):
            self.tts.speak("Ending the interview session. Thank you for your time!", block=True)
            self._complete()
            return "exit"

        if low.startswith("repeat"):
            if self.last_question:
                self.tts.speak(self.last_question)
            return "repeat"

        if "skip" in low:
            with self._lock:
                self._answer_buf.clear()
            return self._ask_next()

        with self._lock:
            self._answer_buf.append(text)

        end_keywords = ["that's it", "i'm done", "that is all", "i'm finished", "that's all"]
        if any(k in low for k in end_keywords):
            self._cancel_timer()
            self._finalize_answer_if_any()
            return "finalized"

        self._schedule_finalize()
        return "collecting"



























'''import datetime
import os
import threading

from file_loaders import load_text
from gemini_question_generator import (
    generate_seed_questions,
    generate_followup_question,
)

class InterviewProcessor:
    SILENCE_SECONDS = 10.0

    def __init__(self, tts):
        self.tts = tts
        self.active = True
        self.resume_text = ""
        self.jd_text = ""
        self.q = ["Tell me about yourself."]
        self.i = -1
        self.last_question = ""
        self.transcript = []
        self._answer_buf = []
        self._silence_timer = None
        self._lock = threading.Lock()
        self.max_questions = 3  # total cap
        self.on_complete = None  # optional callback (GUI/CLI can set)

    # ----------------- file loaders -----------------
    def load_resume(self, path: str):
        self.resume_text = (load_text(path) or "").strip()

    def load_job_description(self, path: str):
        self.jd_text = (load_text(path) or "").strip()

    # ----------------- lifecycle -----------------
    def start_interview(self):
        self.active = True
        self.i = -1
        self.transcript.clear()
        self._answer_buf.clear()
        self._cancel_timer()

        # seed tailored questions (insert after opener)
        if self.jd_text or self.resume_text:
            seeds = generate_seed_questions(
                self.resume_text,
                self.jd_text,
                n=min(2, self.max_questions),
            )
            self.q = ["Tell me about yourself."] + [s for s in seeds if s]
            self.q = self.q[:self.max_questions]

        self.tts.speak(
            "Hi I am your AI Assistant. I’ll interview you. Say 'skip' to move on, 'repeat' to hear a question again, or 'that's it' after completing your answer."
        )
        self._ask_next()

    def _ask_next(self):
        with self._lock:
            self._answer_buf.clear()
            self._cancel_timer()
            self.i += 1
            if self.i >= self.max_questions or self.i >= len(self.q):
                self.tts.speak("That’s all I had. Thanks for your time. Would you like quick feedback?")
                self._complete()
                return "done"
            self.last_question = self.q[self.i]

        self.tts.speak(self.last_question)
        if self.active:
            self._schedule_finalize()
        return "ask"

    # ----------------- helpers -----------------
    def _ack(self, low_text: str) -> str:
        TECH = {"xgboost", "rag", "langchain", "aws", "terraform", "timeseries", "arima", "llm"}
        PEOPLE = {"team", "stakeholder", "client", "collaborat"}
        if any(k in low_text for k in TECH): return "Got it. Thanks. "
        if any(k in low_text for k in PEOPLE): return "Understood. "
        return "Thanks. "

    def _save_transcript(self):
        if not self.transcript:
            return
        os.makedirs("transcripts", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        txt = os.path.join("transcripts", f"interview_{ts}.txt")
        try:
            with open(txt, "w", encoding="utf-8") as f:
                for qi, (q, a) in enumerate(self.transcript, 1):
                    f.write(f"Q{qi}: {q}\n")
                    f.write(f"A{qi}: {a}\n\n")
            print(f"[TRANSCRIPT] Saved to {os.path.abspath(txt)}")
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
        if not self.active:
            return
        self._cancel_timer()
        t = threading.Timer(self.SILENCE_SECONDS, self._finalize_answer_if_any)
        t.daemon = True
        t.start()
        self._silence_timer = t

    def _complete(self):
        # mark finished, stop timers, save once, and notify
        self.active = False
        self._cancel_timer()
        self._save_transcript()
        if self.on_complete:
            try:
                self.on_complete()
            except Exception:
                pass

    # ----------------- finalize -----------------
    def _finalize_answer_if_any(self):
        if not self.active:
            return

        with self._lock:
            answer = " ".join(self._answer_buf).strip()
            self._answer_buf.clear()

        if not answer:
            if not self.active:
                return
            self.tts.speak("If you’re ready, please answer now or say skip.")
            return

        with self._lock:
            q = self.q[self.i] if 0 <= self.i < len(self.q) else ""

        low = answer.lower()
        followup = ""
        if "strength" in q.lower() and len(answer.split()) < 15:
            followup = " Please add one concrete example with measurable impact."
        if "challenging problem" in q.lower() and ("impact" not in low and "result" not in low):
            followup += " Also cover the impact or result in one line."

        new_q = generate_followup_question(answer)

        with self._lock:
            self.transcript.append((q, answer))
            if new_q and new_q not in self.q and len(self.q) < self.max_questions:
                self.q.append(new_q)
            done = (self.i + 1) >= self.max_questions

        if done:
            self.tts.speak(
                self._ack(low) + "That’s all I had. We’ll review your answers and our HR will contact you soon.",
                block=True
            )
            self._complete()
            return

        self.tts.speak(self._ack(low) + "Next question." + followup)
        self._ask_next()

    # ----------------- input -----------------
    def process_input(self, text: str):
        if not self.active:
            return

        low = text.lower().strip()

        if any(k in low for k in ["stop interview", "end interview", "exit", "quit"]):
            self.tts.speak("Ending the interview session. Thank you for your time!", block=True)
            self._complete()
            return "exit"

        if low.startswith("repeat"):
            if self.last_question:
                self.tts.speak(self.last_question)
            return "repeat"

        if "skip" in low:
            with self._lock:
                self._answer_buf.clear()
            return self._ask_next()

        with self._lock:
            self._answer_buf.append(text)

        end_keywords = ["that's it", "i'm done", "that is all", "i'm finished", "that's all"]
        if any(k in low for k in end_keywords):
            self._cancel_timer()
            self._finalize_answer_if_any()
            return "finalized"

        self._schedule_finalize()
        return "collecting"

'''




















