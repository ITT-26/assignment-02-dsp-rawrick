import sounddevice as sd
import pyglet

from audio import choose_input_device
from clock import Clock
from pitch import PitchTracker, cents, detect_major_frequency, CHANNELS, CHUNK_SIZE, RATE
from scoring import ScoreState


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

    def callback(indata, frames, time_info, status):
        if status:
            print(status)
        frequency, rms = detect_major_frequency(indata[:, 0])
        state['freq'], _ = tracker.update(frequency)
        state['rms'] = rms
        now = clock.now()
        active = next((event for event in song.note_events if event.start_time <= now < event.end_time), None)
        if active and state['freq'] > 0 and scores.award(active, cents(state['freq'], active.frequency_hz)):
            state['score'] = scores.score

    try:
        window = pyglet.window.Window(900, 420, caption='Karaoke Game', resizable=True)
        title = pyglet.text.Label('Karaoke', x=20, y=window.height - 24, anchor_x='left', anchor_y='center')
        stats = pyglet.text.Label('', x=20, y=window.height - 52, anchor_x='left', anchor_y='center')
        target = pyglet.text.Label('', x=20, y=window.height - 80, anchor_x='left', anchor_y='center')
        stream = sd.InputStream(device=choose_input_device(input_device), channels=CHANNELS, samplerate=RATE, blocksize=CHUNK_SIZE, callback=callback, latency='low')

        @window.event
        def on_draw():
            window.clear()
            now = clock.now()
            active = next((event for event in song.note_events if event.start_time <= now < event.end_time), None)
            nxt = next((event for event in song.note_events if event.start_time > now), None)
            left = max(0.0, now - lookback)
            right = min(song.duration(), now + lookahead)
            span = max(right - left, 0.01)
            track_left, track_bottom = 180, 120
            track_width = window.width - track_left - 40
            track_height = window.height - track_bottom - 80
            pyglet.shapes.Rectangle(track_left, track_bottom, track_width, track_height, color=(32, 32, 48)).draw()
            pyglet.shapes.Line(track_left, track_bottom + 10, track_left + track_width, track_bottom + 10, color=(90, 90, 120)).draw()
            for event in song.note_events:
                if event.end_time < left or event.start_time > right:
                    continue
                x1 = track_left + ((event.start_time - left) / span) * track_width
                x2 = track_left + ((event.end_time - left) / span) * track_width
                y = track_bottom + 20 + ((event.note - 48) / 36.0) * max(track_height - 40, 1)
                color = (80, 200, 120) if active and event.note == active.note else (120, 140, 180)
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
