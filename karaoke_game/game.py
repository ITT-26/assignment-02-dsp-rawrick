import math
import time

import sounddevice as sd
import pyglet

from audio import choose_input_device
from audio import PitchTracker, cents, detect_major_frequency, CHANNELS, CHUNK_SIZE, RATE
from helper import Clock, ScoreState

def run_game(song, input_device=None, play_midi=False):
    clock = Clock()

    tracker = PitchTracker()
    scores = ScoreState()
    state = {'freq': 0.0, 'rms': 0.0, 'score': 0}
    look_span = 8.0  # seconds shown on screen (centered on playhead)
    countdown_seconds = 3.0
    started = False
    finished = False
    launch_at = time.time()

    def callback(indata, frames, time_info, status):
        if status:
            print(status)
        frequency, rms = detect_major_frequency(indata[:, 0])
        state['freq'], _ = tracker.update(frequency)
        state['rms'] = rms
        if not started or finished:
            return
        now = clock.now()
        active = next((event for event in song.note_events if event.start_time <= now < event.end_time), None)
        if active and state['freq'] > 0 and scores.award(active, cents(state['freq'], active.frequency_hz)):
            state['score'] = scores.score

    try:
        window = pyglet.window.Window(900, 420, caption='Karaoke Game', resizable=True)
        title = pyglet.text.Label('Karaoke', x=window.width // 2, y=window.height - 24, anchor_x='center', anchor_y='center')
        score_label = pyglet.text.Label('', x=window.width // 2, y=window.height - 52, anchor_x='center', anchor_y='center')
        countdown_label = pyglet.text.Label('', x=window.width // 2, y=window.height // 2 + 30, anchor_x='center', anchor_y='center', font_size=28)
        result_label = pyglet.text.Label('', x=window.width // 2, y=window.height // 2 + 36, anchor_x='center', anchor_y='center', font_size=22)
        accuracy_label = pyglet.text.Label('', x=window.width // 2, y=window.height // 2 - 2, anchor_x='center', anchor_y='center', font_size=18)
        instruction_label = pyglet.text.Label('Press space to restart or q to quit', x=window.width // 2, y=80, anchor_x='center', anchor_y='center', font_size=12)
        stream = sd.InputStream(device=choose_input_device(input_device), channels=CHANNELS, samplerate=RATE, blocksize=CHUNK_SIZE, callback=callback, latency='low')

        def ensure_started():
            nonlocal started
            if started:
                return
            started = True
            if play_midi:
                clock.start_midi_play(song.source_path)
            else:
                clock.start_realtime()

        def reset_round():
            nonlocal started, finished, launch_at, scores, state
            started = False
            finished = False
            launch_at = time.time()
            scores = ScoreState()
            state = {'freq': 0.0, 'rms': 0.0, 'score': 0}
            clock.t0 = None

        def mark_misses(now):
            for event in song.note_events:
                if event.end_time <= now:
                    scores.miss(event)

        def accuracy_percent():
            total = scores.hits + scores.misses
            return 0.0 if total <= 0 else (scores.hits / total) * 100.0

        @window.event
        def on_key_press(symbol, modifiers):
            if symbol == pyglet.window.key.Q:
                pyglet.app.exit()
            elif symbol == pyglet.window.key.SPACE:
                reset_round()

        @window.event
        def on_draw():
            nonlocal finished
            window.clear()
            display_time = song.duration() if finished else (clock.now() if started else 0.0)
            active = next((event for event in song.note_events if event.start_time <= display_time < event.end_time), None)
            # keep a constant visible span centered on the playhead
            span = max(0.01, look_span)
            left = display_time - (span / 2.0)
            right = left + span
            track_width = min(window.width - 120, 780)
            track_left = (window.width - track_width) / 2.0
            track_bottom = 120
            track_height = window.height - track_bottom - 80
            pyglet.shapes.Rectangle(track_left, track_bottom, track_width, track_height, color=(32, 32, 48)).draw()
            pyglet.shapes.Line(track_left, track_bottom + 10, track_left + track_width, track_bottom + 10, color=(90, 90, 120)).draw()

            # draw notes centered around the fixed playhead
            for event in song.note_events:
                if event.end_time < left or event.start_time > right:
                    continue
                x1 = track_left + ((event.start_time - left) / span) * track_width
                x2 = track_left + ((event.end_time - left) / span) * track_width
                y = track_bottom + 20 + ((event.note - 48) / 36.0) * max(track_height - 40, 1)
                color = (80, 200, 120) if (event.start_time <= display_time < event.end_time) else (120, 140, 180)
                pyglet.shapes.Rectangle(x1, y - 8, max(x2 - x1, 2), 16, color=color).draw()

            # fixed playhead in the center of the track
            cursor_x = track_left + track_width / 2.0
            pyglet.shapes.Line(cursor_x, track_bottom, cursor_x, track_bottom + track_height, color=(245, 245, 255)).draw()

            # draw current detected frequency as a vertical marker at the center x
            freq = state.get('freq', 0.0)
            if freq and freq > 0.0:
                try:
                    note_val = 69.0 + 12.0 * math.log2(freq / 440.0)
                except Exception:
                    note_val = 69.0
                yf = track_bottom + 20 + ((note_val - 48.0) / 36.0) * max(track_height - 40, 1)
                yf = max(track_bottom + 10, min(track_bottom + track_height - 10, yf))
                pyglet.shapes.Rectangle(cursor_x - 4, yf - 6, 8, 12, color=(240, 120, 80)).draw()

            score_label.text = f"Score: {state['score']}"

            if not started:
                remaining = max(0.0, countdown_seconds - (time.time() - launch_at))
                countdown_label.text = '' if remaining <= 0 else f'{int(math.ceil(remaining))}'
                countdown_label.x = track_left + track_width / 4.0
                countdown_label.draw()
            else:
                countdown_label.text = ''

            if started and not finished:
                mark_misses(clock.now())
                if clock.now() >= song.duration():
                    finished = True

            if finished:
                result_label.text = f"Final score: {scores.score}"
                accuracy_label.text = f"Accuracy: {accuracy_percent():.2f}%"
                result_label.x = track_left + 3.0 * track_width / 4.0
                accuracy_label.x = track_left + 3.0 * track_width / 4.0
                result_label.draw()
                accuracy_label.draw()
                instruction_label.draw()

            title.draw(); score_label.draw()

        def tick(dt):
            if not started and (time.time() - launch_at) >= countdown_seconds:
                ensure_started()

        with stream:
            pyglet.clock.schedule_interval(tick, 1 / 30.0)
            pyglet.app.run()
    except ImportError:
        print('Install pyglet and sounddevice for game mode')
