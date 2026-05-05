import threading
import time

import mido


NOTE_HIT_CENTS = 100.0


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


class ScoreState:
    def __init__(self):
        self.score = 0
        self.hits = 0
        self.misses = 0
        self.scored = set()

    def award(self, event, cents_off):
        if event is None or event.note in self.scored or abs(cents_off) > NOTE_HIT_CENTS:
            return False
        self.score += 100
        self.hits += 1
        self.scored.add(event.note)
        return True

    def miss(self, event):
        if event is None or event.note in self.scored:
            return False
        self.misses += 1
        return True
