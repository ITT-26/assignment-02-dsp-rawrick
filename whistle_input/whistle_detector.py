from collections import deque

import numpy as np


SAMPLE_RATE = 44100
BLOCK_SIZE = 512
MIN_FREQUENCY = 700.0
MAX_FREQUENCY = 3500.0
MIN_RMS = 0.02
HISTORY_SIZE = 6
MIN_SWEEP_HZ = 180.0
COOLDOWN_SECONDS = 0.35


class WhistleDetector:
    def __init__(self):
        self._frequencies = deque(maxlen=HISTORY_SIZE)
        self._cooldown_until = 0.0
        self._sample_index = 0

    # based on audio returns up (upwards chirp), down (downwards chirp)
    def process(self, samples):
        if samples.size == 0:
            return None

        samples = np.asarray(samples, dtype=np.float32)
        rms = float(np.sqrt(np.mean(samples * samples)))
        if rms < MIN_RMS:
            self._frequencies.clear()
            return None

        frequency = self._estimate_frequency(samples)
        if frequency is None:
            return None

        self._frequencies.append(frequency)
        self._sample_index += samples.size

        if len(self._frequencies) < HISTORY_SIZE:
            return None

        current_time = self._sample_index / SAMPLE_RATE
        if current_time < self._cooldown_until:
            return None

        direction = self._classify_direction()
        if direction is None:
            return None

        self._cooldown_until = current_time + COOLDOWN_SECONDS
        self._frequencies.clear()
        return direction

    def _estimate_frequency(self, samples):
        window = np.hanning(samples.size)
        spectrum = np.fft.rfft(samples * window)
        magnitudes = np.abs(spectrum)
        frequencies = np.fft.rfftfreq(samples.size, d=1.0 / SAMPLE_RATE)

        band_mask = (frequencies >= MIN_FREQUENCY) & (frequencies <= MAX_FREQUENCY)
        if not np.any(band_mask):
            return None

        band_magnitudes = magnitudes[band_mask]
        if float(np.max(band_magnitudes)) < 1e-6:
            return None

        band_frequencies = frequencies[band_mask]
        dominant_index = int(np.argmax(band_magnitudes))
        dominant_frequency = float(band_frequencies[dominant_index])
        return dominant_frequency

    def _classify_direction(self):
        values = np.array(self._frequencies, dtype=np.float32)
        change = float(values[-1] - values[0])
        if abs(change) < MIN_SWEEP_HZ:
            return None

        upward_steps = 0
        downward_steps = 0
        for previous, current in zip(values, values[1:]):
            if current > previous:
                upward_steps += 1
            elif current < previous:
                downward_steps += 1

        if upward_steps >= downward_steps + 2 and change > 0:
            return "up"
        if downward_steps >= upward_steps + 2 and change < 0:
            return "down"
        return None
