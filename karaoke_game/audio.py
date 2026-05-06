import math

import numpy as np
import sounddevice as sd

from helper import Clock, ScoreState


CHANNELS = 1
CHUNK_SIZE = 1024
RATE = 44100
MIN_RMS = 0.01
MIN_FREQ = 70.0
MAX_FREQ = 1200.0
PITCH_HISTORY_SIZE = 5
PITCH_SPREAD = 25.0


def cents(actual, target):
    # convert frequency ratio to cents difference
    return 0.0 if actual <= 0 or target <= 0 else 1200.0 * math.log(actual / target, 2.0)


class PitchTracker:
    def __init__(self):
        self.history = []

    # update history and return median frequency and confidence
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
    # detect the dominant frequency with a clipped autocorrelation search
    rms = math.sqrt(np.mean(data * data))
    if rms < MIN_RMS:
        return 0.0, rms

    signal = np.asarray(data, dtype=np.float32)
    signal = signal - np.mean(signal)
    signal = signal * np.hanning(len(signal))
    peak = np.max(np.abs(signal))
    if peak <= 1e-8:
        return 0.0, rms

    # remove low-energy detail so harmonics do not dominate the correlation peak
    clipped = np.where(np.abs(signal) >= 0.3 * peak, signal, 0.0)
    if not np.any(clipped):
        clipped = signal

    corr = np.correlate(clipped, clipped, mode='full')[len(clipped) - 1:]
    corr[0] = 0.0
    if corr[0] == 0.0:
        corr = corr / (np.max(corr) + 1e-8)

    min_lag = max(1, int(RATE / MAX_FREQ))
    max_lag = min(len(corr) - 1, int(RATE / MIN_FREQ))
    if min_lag >= max_lag:
        return 0.0, rms

    window = corr[min_lag:max_lag + 1]
    if window.size == 0:
        return 0.0, rms

    local_maxima = []
    for offset in range(1, len(window) - 1):
        if window[offset] >= window[offset - 1] and window[offset] >= window[offset + 1]:
            local_maxima.append(offset)

    if local_maxima:
        best_offset = max(local_maxima, key=lambda idx: window[idx])
    else:
        best_offset = int(np.argmax(window))

    lag = min_lag + best_offset
    if corr[lag] < 0.2:
        return 0.0, rms

    return float(RATE / lag), rms


def choose_input_device(default=None):
    # prompt user to choose an input device (or return provided default)
    if default is not None:
        return default
    devices = sd.query_devices()
    inputs = [index for index, device in enumerate(devices) if device['max_input_channels'] > 0]
    for index in inputs:
        print(index, devices[index]['name'])
    try:
        value = input('Select input device (Enter for default): ').strip()
        return None if value == '' else int(value)
    except Exception:
        return None


def listen_for_frequency(song, clock=None, input_device=None):
    # open the input stream and continuously detect frequency + score notes
    clock = clock or Clock()
    if clock.t0 is None:
        clock.start_realtime()
    tracker = PitchTracker()
    scores = ScoreState()
    last_print = [0.0]
    device = choose_input_device(input_device)

    # input stream callback: analyze buffer, update tracker and scoring
    def callback(indata, frames, time_info, status):
        if status:
            print(status)
        frequency, rms = detect_major_frequency(indata[:, 0])
        stable, _ = tracker.update(frequency)
        now = clock.now()
        active = next((event for event in song.note_events if event.start_time <= now < event.end_time), None)
        if active and stable > 0:
            scores.award(active, cents(stable, active.frequency_hz))
        if now - last_print[0] >= 0.1:
            print(f"{now:.2f}s freq={stable:.1f}Hz rms={rms:.3f} score={scores.score}")
            last_print[0] = now

    with sd.InputStream(device=device, channels=CHANNELS, samplerate=RATE, blocksize=CHUNK_SIZE, callback=callback, latency='low'):
        try:
            while True:
                sd.sleep(200)
        except KeyboardInterrupt:
            print('\nStopped')
