import sounddevice as sd

from pitch import PitchTracker, cents, detect_major_frequency, CHANNELS, CHUNK_SIZE, RATE
from scoring import ScoreState
from clock import Clock


def choose_input_device(default=None):
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
    clock = clock or Clock()
    if clock.t0 is None:
        clock.start_realtime()
    tracker = PitchTracker()
    scores = ScoreState()
    last_print = [0.0]
    device = choose_input_device(input_device)

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
