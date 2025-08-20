import pyttsx3
import threading
import queue

class TextToSpeech:
    """Threaded pyttsx3 with start/stop hooks so we can pause STT while speaking."""
    def __init__(self, rate=150, voice_index=1, on_start=None, on_end=None):
        self.rate = rate
        self.voice_index = voice_index
        self.on_start = on_start
        self.on_end = on_end

        self.queue = queue.Queue()
        self._processing = False
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _speak_once(self, text: str):
        engine = pyttsx3.init()
        engine.setProperty('rate', self.rate)
        voices = engine.getProperty('voices')
        if 0 <= self.voice_index < len(voices):
            engine.setProperty('voice', voices[self.voice_index].id)
        engine.say(text)
        engine.runAndWait()
        engine.stop()

    def _run_loop(self):
        while True:
            text, block_event = self.queue.get()
            self._processing = True
            try:
                if self.on_start:
                    try: self.on_start()
                    except Exception: pass
                print(f"AI (speaking): {text}")
                self._speak_once(text)
            except Exception as e:
                print(f"[TTS Error] {e}")
            finally:
                if self.on_end:
                    try: self.on_end()
                    except Exception: pass
                self._processing = False
                if block_event:
                    block_event.set()

    def speak(self, text: str, block: bool = False):
        if not text or not text.strip():
            return
        block_event = threading.Event() if block else None
        self.queue.put((text, block_event))
        if block and block_event:
            block_event.wait()

    def is_speaking(self) -> bool:
        return self._processing