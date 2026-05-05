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
    # detect the dominant frequency in the buffer and return (freq, rms)
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
