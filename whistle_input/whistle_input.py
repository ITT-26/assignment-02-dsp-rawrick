import numpy as np
import sounddevice as sd

# audio settings for the whistle detector
SAMPLE_RATE = 44100
BLOCK_SIZE = 512
MIN_FREQUENCY = 700.0
MAX_FREQUENCY = 3500.0
MIN_RMS = 0.02
HISTORY_SIZE = 6
MIN_SWEEP_HZ = 180.0
COOLDOWN_SECONDS = 0.35


class WhistleDetector:
    # keep a short history of recent frequency estimates

    def __init__(self):
        self.history = []
        self.cooldown_until = 0.0
        self.sample_index = 0

    def process(self, samples):
        # analyze one audio block and return up or down
        if samples.size == 0:
            return None

        samples = np.asarray(samples, dtype=np.float32)
        rms = float(np.sqrt(np.mean(samples * samples)))
        if rms < MIN_RMS:
            self.history.clear()
            return None

        freq = self.estimate_frequency(samples)
        if freq is None:
            return None

        self.history.append(freq)
        if len(self.history) > HISTORY_SIZE:
            self.history.pop(0)

        self.sample_index += samples.size
        if len(self.history) < HISTORY_SIZE:
            return None

        current_time = self.sample_index / SAMPLE_RATE
        if current_time < self.cooldown_until:
            return None

        direction = self.classify_direction()
        if direction is None:
            return None

        self.cooldown_until = current_time + COOLDOWN_SECONDS
        self.history.clear()
        return direction

    def estimate_frequency(self, samples):
        # find the strongest frequency in the whistle range
        window = np.hanning(len(samples))
        spectrum = np.fft.rfft(samples * window)
        mags = np.abs(spectrum)
        freqs = np.fft.rfftfreq(len(samples), d=1.0 / SAMPLE_RATE)

        mask = (freqs >= MIN_FREQUENCY) & (freqs <= MAX_FREQUENCY)
        if not mask.any():
            return None

        band = mags[mask]
        if float(band.max()) < 1e-6:
            return None

        bf = freqs[mask]
        return float(bf[band.argmax()])

    def classify_direction(self):
        # compare the first and last values in the history
        values = np.array(self.history, dtype=np.float32)
        change = float(values[-1] - values[0])
        if abs(change) < MIN_SWEEP_HZ:
            return None

        up = 0
        down = 0
        for a, b in zip(values, values[1:]):
            if b > a:
                up += 1
            elif b < a:
                down += 1

        if up >= down + 2 and change > 0:
            return 'up'
        if down >= up + 2 and change < 0:
            return 'down'
        return None


def open_input_stream(detector, on_direction, device=None):
    # open the audio stream and call the handler on each whistle

    def callback(indata, frames, time_info, status):
        if status:
            print(status)
        try:
            d = detector.process(indata[:, 0])
            if d is not None:
                on_direction(d)
        except Exception:
            # keep audio running even if detection is interrupted
            pass

    return sd.InputStream(
        device=device,
        channels=1,
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        callback=callback,
        latency='low',
    )
