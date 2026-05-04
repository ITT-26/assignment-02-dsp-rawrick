import threading
import time

import mido


class Clock:
    def __init__(self):
        self.t0 = None

    def start_realtime(self):
        self.t0 = time.time()

    def start_midi_play(self, path):
        def run():
            self.t0 = time.time()
            for _ in mido.MidiFile(path).play():
                pass

        threading.Thread(target=run, daemon=True).start()

    def now(self):
        return 0.0 if self.t0 is None else time.time() - self.t0
