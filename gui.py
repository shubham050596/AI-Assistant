import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import sys
import os
import time

from text_to_speech import TextToSpeech
from whisper_transcriber import WhisperTranscriber
from interview_processor import InterviewProcessor


class StdoutRedirector:
    """Redirect prints to the Tkinter text area."""
    def __init__(self, widget):
        self.widget = widget

    def write(self, s):
        if not s:
            return
        try:
            self.widget.configure(state="normal")
            self.widget.insert(tk.END, s)
            self.widget.see(tk.END)
            self.widget.configure(state="disabled")
        except tk.TclError:
            pass

    def flush(self):
        pass


class AIInterviewAssistant:
    """Interview loop controllable from GUI."""
    def __init__(self, on_finished=None):
        self.tts = TextToSpeech()
        self.processor = InterviewProcessor(self.tts)
        self.stt = WhisperTranscriber(on_text=self.process_user_input)

        # Pause mic during AI speech
        self.tts.on_start = getattr(self.stt, "pause", None)
        self.tts.on_end = getattr(self.stt, "resume", None)

        self.running = False
        self.thread = None
        self.on_finished = on_finished  # GUI callback when we finish

        # also wire processor callback (no-op if GUI not provided)
        self.processor.on_complete = self.stop

    def process_user_input(self, text):
        print(f"User: {text}")
        result = self.processor.process_input(text)
        if result == "exit":
            self.stop()

    def start(self, resume_path: str = "", jd_path: str = ""):
        # Load files if provided
        if resume_path:
            self.processor.load_resume(resume_path)
        if jd_path:
            self.processor.load_job_description(jd_path)

        if self.running:
            return

        def _run():
            try:
                self.running = True
                self.processor.start_interview()
                self.stt.start()

                # keep thread alive while running
                while self.running:
                    # Auto-stop when interview ends
                    if not self.processor.active:
                        self.stop()
                        break
                    time.sleep(0.1)
            except Exception as e:
                print(f"[GUI] Error: {e}")
                self.stop()

        self.thread = threading.Thread(target=_run, daemon=True)
        self.thread.start()

    def stop(self):
        """Idempotent clean shutdown + finalize transcript once."""
        if not self.running:
            # still invoke GUI callback so window can react (if needed)
            if callable(self.on_finished):
                try:
                    self.on_finished()
                except Exception:
                    pass
            return

        self.running = False

        try:
            self.stt.stop()
        except Exception:
            pass

        try:
            self.processor._cancel_timer()
            self.processor._finalize_answer_if_any()
            self.processor._save_transcript()
        except Exception:
            pass

        print("\nSession ended. Goodbye!")

        if callable(self.on_finished):
            try:
                self.on_finished()
            except Exception:
                pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Interview Assistant")
        self.geometry("780x520")

        # Paths
        self.resume_path = tk.StringVar()
        self.jd_path = tk.StringVar()

        # Top controls
        frm = tk.Frame(self)
        frm.pack(fill=tk.X, padx=10, pady=10)

        # Resume picker
        tk.Label(frm, text="Resume:").grid(row=0, column=0, sticky="w")
        tk.Entry(frm, textvariable=self.resume_path, width=70).grid(row=0, column=1, padx=6)
        tk.Button(frm, text="Browse", command=self.pick_resume).grid(row=0, column=2)

        # JD picker
        tk.Label(frm, text="Job Description:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Entry(frm, textvariable=self.jd_path, width=70).grid(row=1, column=1, padx=6, pady=(6, 0))
        tk.Button(frm, text="Browse", command=self.pick_jd).grid(row=1, column=2, pady=(6, 0))

        # Start/Stop
        btns = tk.Frame(self)
        btns.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.start_btn = tk.Button(btns, text="Start Interview", command=self.start_interview)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = tk.Button(btns, text="Stop", command=self.stop_interview)
        self.stop_btn.pack(side=tk.LEFT, padx=8)

        # Log output
        self.log = scrolledtext.ScrolledText(self, height=22, state="disabled")
        self.log.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Redirect prints to the log
        sys.stdout = StdoutRedirector(self.log)

        # Assistant: finish callback posts back to Tk main thread
        self.assistant = AIInterviewAssistant(
            on_finished=lambda: self.after(0, self._on_assistant_finished)
        )

        # Gemini key check helper
        if not os.environ.get("GOOGLE_API_KEY"):
            messagebox.showinfo(
                "Missing GOOGLE_API_KEY",
                "GOOGLE_API_KEY is not set. Set it in your environment before starting."
            )

        self.protocol("WM_DELETE_WINDOW", self.on_close)
    def _on_assistant_finished(self):
        try:
            res = self.assistant.processor.last_result or {}
            score = res.get("score")
            verdict = res.get("verdict")
            if score is not None and verdict:
                msg = f"Interview completed.\nScore: {score}/100\nVerdict: {verdict}\n\nTranscript saved in transcripts/."
            else:
                msg = "Interview completed.\nTranscript saved in transcripts/."
            messagebox.showinfo("Interview finished", msg)
        except tk.TclError:
            pass
        # close the window
        self.on_close()







   


    '''def _on_assistant_finished(self):
        # Friendly popup; detailed path is printed by InterviewProcessor
        try:
            messagebox.showinfo("Interview finished", "Transcript saved in the transcripts/ folder.")
        except tk.TclError:
            pass
        # Auto-close window
        self.on_close()'''

    def pick_resume(self):
        path = filedialog.askopenfilename(
            title="Select Resume",
            filetypes=[("Documents", "*.txt *.pdf *.docx"), ("All Files", "*.*")]
        )
        if path:
            self.resume_path.set(path)

    def pick_jd(self):
        path = filedialog.askopenfilename(
            title="Select Job Description",
            filetypes=[("Documents", "*.txt *.pdf *.docx"), ("All Files", "*.*")]
        )
        if path:
            self.jd_path.set(path)

    def start_interview(self):
        self.assistant.start(
            resume_path=self.resume_path.get().strip(),
            jd_path=self.jd_path.get().strip()
        )

    def stop_interview(self):
        self.assistant.stop()

    def on_close(self):
        # Try to stop gracefully; then destroy window
        try:
            self.assistant.stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    App().mainloop()



















