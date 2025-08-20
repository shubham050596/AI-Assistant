import sounddevice as sd
import numpy as np
import queue as _queue
import threading as _threading
from faster_whisper import WhisperModel
import time

class WhisperTranscriber:
    def __init__(
        self,
        on_text,
        model_size="base",
        device="cpu",
        compute_type="int8",
        samplerate=16000,
        block_duration=0.5,   # seconds
        chunk_duration=3.0,   # seconds (slightly longer to reduce fragments)
        channels=1,
        language="en"
    ):
        self.on_text = on_text
        self.samplerate = samplerate
        self.channels = channels
        self.block_duration = block_duration
        self.chunk_duration = chunk_duration
        self.frames_per_block = int(samplerate * block_duration)
        self.frames_per_chunk = int(samplerate * chunk_duration)
        self.language = language

        self.audio_queue = _queue.Queue()
        self.audio_buffer = []
        self.running = False
        self.paused = False  # new: half-duplex pause flag
        self._last_emit = ""
        self._last_emit_ts = 0.0

        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(status)
        # Always enqueue, we will drop in the worker if paused
        self.audio_queue.put(indata.copy())

    def _recorder(self):
        with sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            callback=self._audio_callback,
            blocksize=self.frames_per_block
        ):
            while self.running:
                sd.sleep(100)

    def _emit_ok(self, text: str) -> bool:
        now = time.time()
        text_norm = text.strip()
        if not text_norm:
            return False
        # Drop 1-2 word fillers
        if len(text_norm.split()) <= 1:
            return False
        # Debounce near-duplicates within 1.5s
        if text_norm.lower() == self._last_emit.lower() and (now - self._last_emit_ts) < 1.5:
            return False
        self._last_emit = text_norm
        self._last_emit_ts = now
        return True

    def _transcriber(self):
        try:
            while self.running:
                block = self.audio_queue.get()
                if block is None:
                    break
                if self.paused:
                    # Drop incoming audio while paused to avoid feedback
                    self.audio_buffer = []
                    continue

                self.audio_buffer.append(block)
                total_frames = sum(len(b) for b in self.audio_buffer)
                if total_frames >= self.frames_per_chunk:
                    audio_data = np.concatenate(self.audio_buffer)[:self.frames_per_chunk]
                    self.audio_buffer = []
                    audio_data = audio_data.flatten().astype(np.float32)

                    segments, _ = self.model.transcribe(
                        audio_data,
                        language=self.language,
                        beam_size=1,
                        vad_filter=True,
                        condition_on_previous_text=False
                    )
                    text_out = "".join([seg.text for seg in segments]).strip()
                    if text_out and self._emit_ok(text_out):
                        # Do NOT print here; let main print for consistent UX
                        self.on_text(text_out)
        except Exception as e:
            print(f"[WhisperTranscriber] Error: {e}")

    def start(self):
        if self.running:
            return
        self.running = True
        self.rec_thread = _threading.Thread(target=self._recorder, daemon=True)
        self.asr_thread = _threading.Thread(target=self._transcriber, daemon=True)
        self.rec_thread.start()
        self.asr_thread.start()
        print("Listening... Say 'stop interview' to exit (Ctrl+C to quit).")

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.audio_queue.put(None)
        print("Stopped listening.")

    # New: half-duplex controls
    def pause(self):
        self.paused = True
        self.audio_buffer = []

    def resume(self):
        self.paused = False
