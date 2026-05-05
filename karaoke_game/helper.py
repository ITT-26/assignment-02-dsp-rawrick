import threading
import time

import mido


NOTE_HIT_CENTS = 100.0


# tracks game time
class Clock:
    def __init__(self):
        self.t0 = None

    # time from now
    def start_realtime(self):
        self.t0 = time.time()

    # time from MIDI file start
    def start_midi_play(self, path):
        def run():
            self.t0 = time.time()
            for _ in mido.MidiFile(path).play():
                pass

        threading.Thread(target=run, daemon=True).start()

    # current time in seconds
    def now(self):
        return 0.0 if self.t0 is None else time.time() - self.t0


# tracks player score
class ScoreState:
    def __init__(self):
        self.score = 0
        self.hits = 0
        self.misses = 0
        self.scored = set()

    # true on hit, false on miss/already scored
    def award(self, event, cents_off):
        if event is None or event.note in self.scored or abs(cents_off) > NOTE_HIT_CENTS:
            return False
        self.score += 100
        self.hits += 1
        self.scored.add(event.note)
        return True

    # true on miss, false on hit/already scored
    def miss(self, event):
        if event is None or event.note in self.scored:
            return False
        self.misses += 1
        return True
