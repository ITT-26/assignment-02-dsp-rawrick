import argparse
import math
import time
import threading
import mido
import numpy as np
import sounddevice as sd
import pyglet


# compact settings
CHUNK_SIZE, RATE, CHANNELS = 1024, 44100, 1
MIN_RMS, MIN_FREQ, MAX_FREQ = 0.01, 70.0, 1200.0
PITCH_HISTORY_SIZE, PITCH_SPREAD = 5, 25.0
NOTE_HIT_CENTS = 50.0


class Clock:
    def __init__(self): self.t0 = None
    def start_realtime(self): self.t0 = time.time()

    def start_midi_play(self, p):
        def r():
            self.t0 = time.time()
            for _ in mido.MidiFile(p).play():
                pass
        threading.Thread(target=r, daemon=True).start()

    def now(self): return 0.0 if self.t0 is None else time.time() - self.t0


class NoteEvent:
    def __init__(self, n, s, e, v):
        self.note = n
        self.frequency_hz = 440.0 * 2 ** ((n - 69) / 12.0)
        self.start_time = s
        self.end_time = e
        self.velocity = v


class SongData:
    def __init__(self, path, ticks, events):
        self.source_path = path
        self.ticks_per_beat = ticks
        self.note_events = events

    def duration(self):
        return max((ev.end_time for ev in self.note_events), default=0.0)


def load_song(path):
    mf = mido.MidiFile(path)
    cur_t, tempo = 0.0, 500000
    open_notes = {}
    events = []
    for msg in mido.merge_tracks(mf.tracks):
        cur_t += mido.tick2second(msg.time, mf.ticks_per_beat, tempo)
        if msg.type == 'set_tempo':
            tempo = msg.tempo
            continue
        if msg.type == 'note_on' and msg.velocity > 0:
            open_notes.setdefault(msg.note, []).append((cur_t, msg.velocity))
            continue
        if msg.type in ('note_off', 'note_on'):
            stack = open_notes.get(msg.note)
            if not stack:
                continue
            s, v = stack.pop()
            events.append(NoteEvent(msg.note, s, cur_t, v))
    for n, stack in open_notes.items():
        while stack:
            s, v = stack.pop()
            events.append(NoteEvent(n, s, cur_t, v))
    events.sort(key=lambda e: (e.start_time, e.note, e.end_time))
    return SongData(path, mf.ticks_per_beat, events)


def fmt(ev):
    return f"note={ev.note} freq={ev.frequency_hz:.2f}Hz start={ev.start_time:.3f}s end={ev.end_time:.3f}s dur={ev.end_time-ev.start_time:.3f}s vel={ev.velocity}"


def cents(a, b):
    return 0.0 if a <= 0 or b <= 0 else 1200.0 * math.log(a / b, 2.0)


class PitchTracker:
    def __init__(self): self.h = []

    def update(self, f):
        if f > 0:
            self.h.append(f)
        if len(self.h) > PITCH_HISTORY_SIZE:
            self.h.pop(0)
        v = [x for x in self.h if x > 0]
        if len(v) < 3:
            return 0.0, 0.0
        v = sorted(v)
        med = v[len(v)//2]
        conf = 1.0 - min((v[-1]-v[0]) / PITCH_SPREAD, 1.0)
        return med, conf


class ScoreState:
    def __init__(self):
        self.score = 0
        self.hits = 0
        self.misses = 0
        self.scored = set()

    def award(self, ev, cents_off):
        if ev is None or ev.note in self.scored or abs(cents_off) > NOTE_HIT_CENTS:
            return False
        self.score += 100
        self.hits += 1
        self.scored.add(ev.note)
        return True

    def miss(self, ev):
        if ev is None or ev.note in self.scored:
            return False
        self.misses += 1
        return True


def detect_major_frequency(data):
    rms = math.sqrt(np.mean(data * data))
    if rms < MIN_RMS:
        return 0.0, rms
    w = np.hanning(len(data))
    S = np.abs(np.fft.rfft(data * w))
    f = np.fft.rfftfreq(len(data), 1.0 / RATE)
    mask = (f >= MIN_FREQ) & (f <= MAX_FREQ)
    if not np.any(mask):
        return 0.0, rms
    idx = np.argmax(S[mask])
    freqs = f[mask]
    return float(freqs[idx]), rms


def choose_input_device(default=None):
    if default is not None:
        return default
    devs = sd.query_devices()
    ins = [i for i, d in enumerate(devs) if d['max_input_channels'] > 0]
    for i in ins:
        print(i, devs[i]['name'])
    try:
        t = input('Select input device (Enter for default): ').strip()
        return None if t == '' else int(t)
    except Exception:
        return None


def listen_for_frequency(song, clock=None, input_device=None):
    if clock is None:
        clock = Clock()
        clock.start_realtime()
    dev = choose_input_device(input_device)
    tracker = PitchTracker()
    scores = ScoreState()
    last_print = [0.0]

    def cb(indata, frames, t, status):
        if status:
            print(status)
        f, rms = detect_major_frequency(indata[:, 0])
        sf, conf = tracker.update(f)
        now = clock.now()
        active = next(
            (ev for ev in song.note_events if ev.start_time <= now < ev.end_time), None)
        if active and sf > 0:
            co = cents(sf, active.frequency_hz)
            scores.award(active, co)
        if now - last_print[0] >= 0.1:
            print(f"{now:.2f}s freq={sf:.1f}Hz rms={rms:.3f} score={scores.score}")
            last_print[0] = now

    with sd.InputStream(device=dev, channels=CHANNELS, samplerate=RATE, blocksize=CHUNK_SIZE, callback=cb, latency='low'):
        try:
            while True:
                sd.sleep(200)
        except KeyboardInterrupt:
            print('\nStopped')


def run_game(song, input_device=None, play_midi=False):
    clock = Clock()
    if play_midi:
        clock.start_midi_play(song.source_path)
    else:
        clock.start_realtime()

    tracker = PitchTracker()
    scores = ScoreState()
    state = {'freq': 0.0, 'rms': 0.0, 'score': 0}
    lookback = 3.0
    lookahead = 5.0

    def cb(indata, frames, t, status):
        if status:
            print(status)
        f, rms = detect_major_frequency(indata[:, 0])
        state['freq'], _ = tracker.update(f)
        state['rms'] = rms
        now = clock.now()
        active = next((ev for ev in song.note_events if ev.start_time <= now < ev.end_time), None)
        if active and state['freq'] > 0:
            if scores.award(active, cents(state['freq'], active.frequency_hz)):
                state['score'] = scores.score

    try:
        window = pyglet.window.Window(900, 420, caption='Karaoke Game', resizable=True)
        title = pyglet.text.Label('Karaoke', x=20, y=window.height - 24, anchor_x='left', anchor_y='center')
        stats = pyglet.text.Label('', x=20, y=window.height - 52, anchor_x='left', anchor_y='center')
        target = pyglet.text.Label('', x=20, y=window.height - 80, anchor_x='left', anchor_y='center')
        stream = sd.InputStream(device=choose_input_device(input_device), channels=CHANNELS, samplerate=RATE, blocksize=CHUNK_SIZE, callback=cb, latency='low')

        @window.event
        def on_draw():
            window.clear()
            now = clock.now()
            active = next((ev for ev in song.note_events if ev.start_time <= now < ev.end_time), None)
            nxt = next((ev for ev in song.note_events if ev.start_time > now), None)
            left = max(0.0, now - lookback)
            right = min(song.duration(), now + lookahead)
            span = max(right - left, 0.01)
            track_left, track_bottom = 180, 120
            track_width = window.width - track_left - 40
            track_height = window.height - track_bottom - 80

            pyglet.shapes.Rectangle(track_left, track_bottom, track_width, track_height, color=(32, 32, 48)).draw()
            pyglet.shapes.Line(track_left, track_bottom + 10, track_left + track_width, track_bottom + 10, color=(90, 90, 120)).draw()

            for ev in song.note_events:
                if ev.end_time < left or ev.start_time > right:
                    continue
                x1 = track_left + ((ev.start_time - left) / span) * track_width
                x2 = track_left + ((ev.end_time - left) / span) * track_width
                y = track_bottom + 20 + ((ev.note - 48) / 36.0) * max(track_height - 40, 1)
                color = (80, 200, 120) if active and ev.note == active.note else (120, 140, 180)
                pyglet.shapes.Rectangle(x1, y - 8, max(x2 - x1, 2), 16, color=color).draw()

            cursor_x = track_left + ((now - left) / span) * track_width
            pyglet.shapes.Line(cursor_x, track_bottom, cursor_x, track_bottom + track_height, color=(245, 245, 255)).draw()

            stats.text = f"Score: {state['score']}   Freq: {state['freq']:.1f} Hz   RMS: {state['rms']:.3f}"
            if active:
                target.text = f"Now: note {active.note}  {active.frequency_hz:.1f} Hz"
            elif nxt:
                target.text = f"Next: note {nxt.note}  {nxt.frequency_hz:.1f} Hz"
            else:
                target.text = 'Done'
            title.draw(); stats.draw(); target.draw()

        def tick(dt):
            if clock.now() >= song.duration() + 0.5:
                pyglet.app.exit()

        with stream:
            pyglet.clock.schedule_interval(tick, 1 / 30.0)
            pyglet.app.run()
    except ImportError:
        print('Install pyglet and sounddevice for game mode')


def build_argument_parser():
    p = argparse.ArgumentParser()
    p.add_argument('midi_file')
    p.add_argument('--limit', type=int, default=10)
    p.add_argument('--listen', action='store_true')
    p.add_argument('--game', action='store_true')
    p.add_argument('--play-midi', action='store_true')
    p.add_argument('--input-device', type=int, default=None)
    return p


def main(argv=None):
    p = build_argument_parser()
    args = p.parse_args(argv)
    try:
        song = load_song(args.midi_file)
    except Exception as e:
        print('Error loading MIDI:', e)
        return 1
    print('Loaded', song.source_path, 'events=', len(
        song.note_events), 'dur=', f"{song.duration():.3f}")
    for ev in song.note_events[:args.limit]:
        print(fmt(ev))
    if args.listen:
        listen_for_frequency(song, None, args.input_device)
    if args.game:
        run_game(song, args.input_device, args.play_midi)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
