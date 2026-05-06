import threading
import time

import mido


NOTE_HIT_CENTS = 130.0
NOTE_GREAT_CENTS = 70.0
NOTE_PERFECT_CENTS = 30.0


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
        self.combo = 0
        self.max_combo = 0
        self.resolved = set()
        self.best_error = {}

    # stable unique key for one note event
    def key(self, event):
        return (event.start_time, event.end_time, event.note)

    # remember best pitch error seen while note is active
    def track_pitch(self, event, cents_off):
        if event is None:
            return False
        note_key = self.key(event)
        if note_key in self.resolved:
            return False
        value = abs(cents_off)
        best = self.best_error.get(note_key)
        if best is None or value < best:
            self.best_error[note_key] = value
            return True
        return False

    # finalize one note after it ends and update score/accuracy once
    def finalize(self, event):
        if event is None:
            return False
        note_key = self.key(event)
        if note_key in self.resolved:
            return False
        self.resolved.add(note_key)
        best = self.best_error.pop(note_key, None)
        if best is None or best > NOTE_HIT_CENTS:
            self.misses += 1
            self.combo = 0
            return True

        self.hits += 1
        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)

        # base points + quality + combo bonus
        quality_bonus = 10
        if best <= NOTE_PERFECT_CENTS:
            quality_bonus = 50
        elif best <= NOTE_GREAT_CENTS:
            quality_bonus = 30
        combo_bonus = min(50, max(0, self.combo - 1) * 5)
        self.score += 100 + quality_bonus + combo_bonus
        return True

    # true on hit, false on miss/already scored
    def award(self, event, cents_off):
        if event is None:
            return False
        self.track_pitch(event, cents_off)
        return self.finalize(event)

    # true on miss, false on hit/already scored
    def miss(self, event):
        return self.finalize(event)
