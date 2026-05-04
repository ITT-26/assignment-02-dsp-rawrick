import math

import numpy as np


CHANNELS = 1
CHUNK_SIZE = 1024
RATE = 44100
MIN_RMS = 0.01
MIN_FREQ = 70.0
MAX_FREQ = 1200.0
PITCH_HISTORY_SIZE = 5
PITCH_SPREAD = 25.0


def cents(actual, target):
    return 0.0 if actual <= 0 or target <= 0 else 1200.0 * math.log(actual / target, 2.0)


class PitchTracker:
    def __init__(self):
        self.history = []

    def update(self, frequency):
        if frequency > 0:
            self.history.append(frequency)
        if len(self.history) > PITCH_HISTORY_SIZE:
            self.history.pop(0)
        values = [value for value in self.history if value > 0]
        if len(values) < 3:
            return 0.0, 0.0
        values.sort()
        middle = values[len(values) // 2]
        confidence = 1.0 - min((values[-1] - values[0]) / PITCH_SPREAD, 1.0)
        return middle, confidence


def detect_major_frequency(data):
    rms = math.sqrt(np.mean(data * data))
    if rms < MIN_RMS:
        return 0.0, rms
    window = np.hanning(len(data))
    spectrum = np.abs(np.fft.rfft(data * window))
    freqs = np.fft.rfftfreq(len(data), 1.0 / RATE)
    mask = (freqs >= MIN_FREQ) & (freqs <= MAX_FREQ)
    if not np.any(mask):
        return 0.0, rms
    return float(freqs[mask][np.argmax(spectrum[mask])]), rms
