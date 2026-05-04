NOTE_HIT_CENTS = 50.0


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
