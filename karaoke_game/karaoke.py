import argparse
import math
import time
import threading

import mido
import numpy as np


# audio settings (kept close to audio_sample.py)
CHUNK_SIZE = 1024
RATE = 44100
CHANNELS = 1
MIN_RMS = 0.01
MIN_FREQ = 70.0
MAX_FREQ = 1200.0
PITCH_HISTORY_SIZE = 5
PITCH_STABLE_SPREAD = 25.0
NOTE_HIT_CENTS = 50.0
NOTE_POINTS = 100
GAME_WINDOW_WIDTH = 1100
GAME_WINDOW_HEIGHT = 720
SONG_LOOKBACK_SECONDS = 3.0
SONG_LOOKAHEAD_SECONDS = 5.0


class NoteEvent:
    def __init__(self, note, frequency_hz, start_time, end_time, velocity):
        self.note = note
        self.frequency_hz = frequency_hz
        self.start_time = start_time
        self.end_time = end_time
        self.velocity = velocity

    def duration(self):
        dur = self.end_time - self.start_time
        return dur


# current midi song
class SongData:
    def __init__(self, source_path, ticks_per_beat, note_events):
        self.source_path = source_path
        self.ticks_per_beat = ticks_per_beat
        self.note_events = note_events

    def duration(self):
        if not self.note_events:
            return 0.0
        max_end = 0.0
        for event in self.note_events:
            if event.end_time > max_end:
                max_end = event.end_time
        return max_end


# note to frequency
def midi_note_to_frequency(note):
    return 440.0 * math.pow(2.0, (note - 69) / 12.0)


def load_song(midi_path):
    path = midi_path
    midi_file = mido.MidiFile(path)

    active_notes = {}
    note_events = []
    current_time = 0.0
    current_tempo = 500000

    # Walk through the MIDI data in time order.
    for message in mido.merge_tracks(midi_file.tracks):
        current_time += mido.tick2second(
            message.time,
            midi_file.ticks_per_beat,
            current_tempo,
        )

        if message.type == "set_tempo":
            current_tempo = message.tempo
            continue

        if message.type == "note_on" and message.velocity > 0:
            if message.note not in active_notes:
                active_notes[message.note] = []
            active_notes[message.note].append((current_time, message.velocity))
            continue

        if message.type in {"note_off", "note_on"}:
            # match each note off with the latest note on
            note_stack = active_notes.get(message.note)
            if not note_stack:
                continue

            start_time, velocity = note_stack.pop()
            note_events.append(
                NoteEvent(
                    message.note,
                    midi_note_to_frequency(message.note),
                    start_time,
                    current_time,
                    velocity,
                )
            )

    # Close any notes that never got a note_off message.
    for note, note_stack in active_notes.items():
        while note_stack:
            start_time, velocity = note_stack.pop()
            note_events.append(
                NoteEvent(
                    note,
                    midi_note_to_frequency(note),
                    start_time,
                    current_time,
                    velocity,
                )
            )

    # Sort by start time, then note, then end time
    for i in range(len(note_events)):
        for j in range(i + 1, len(note_events)):
            event_i = note_events[i]
            event_j = note_events[j]
            swap = False
            if event_i.start_time > event_j.start_time:
                swap = True
            elif event_i.start_time == event_j.start_time and event_i.note > event_j.note:
                swap = True
            elif event_i.start_time == event_j.start_time and event_i.note == event_j.note and event_i.end_time > event_j.end_time:
                swap = True
            
            if swap:
                note_events[i] = event_j
                note_events[j] = event_i

    return SongData(source_path=path, ticks_per_beat=midi_file.ticks_per_beat, note_events=note_events)


# 
def format_note_event(event):
    note_str = f"note={event.note}"
    freq_str = f"freq={event.frequency_hz:.2f}Hz"
    start_str = f"start={event.start_time:.3f}s"
    end_str = f"end={event.end_time:.3f}s"
    dur = event.duration()
    dur_str = f"dur={dur:.3f}s"
    vel_str = f"vel={event.velocity}"
    
    result = note_str + " " + freq_str + " " + start_str + " " + end_str + " " + dur_str + " " + vel_str
    return result


def cents_difference(actual_frequency, target_frequency):
    if actual_frequency <= 0.0 or target_frequency <= 0.0:
        return 0.0
    return 1200.0 * math.log(actual_frequency / target_frequency, 2.0)


def note_name(note_number):
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    name = note_names[note_number % 12]
    octave = (note_number // 12) - 1
    return f"{name}{octave}"


class PitchTracker:
    def __init__(self):
        self.history = []

    def update(self, frequency_hz):
        if frequency_hz > 0.0:
            self.history.append(frequency_hz)

        while len(self.history) > PITCH_HISTORY_SIZE:
            self.history.pop(0)

        valid = []
        for value in self.history:
            if value > 0.0:
                valid.append(value)

        if len(valid) < 3:
            return 0.0, 0.0

        sorted_valid = sorted(valid)
        middle = len(sorted_valid) // 2
        if len(sorted_valid) % 2 == 1:
            stable_frequency = sorted_valid[middle]
        else:
            stable_frequency = (sorted_valid[middle - 1] + sorted_valid[middle]) / 2.0

        spread = sorted_valid[-1] - sorted_valid[0]
        confidence = 1.0 - min(spread / PITCH_STABLE_SPREAD, 1.0)
        return stable_frequency, confidence


class ScoreState:
    def __init__(self):
        self.score = 0
        self.hits = 0
        self.misses = 0
        self.combo = 0
        self.scored_note = None
        self.missed_note = None

    def reset_note_state(self, note_number):
        if self.scored_note != note_number:
            self.scored_note = None
        if self.missed_note != note_number:
            self.missed_note = None

    def award_hit(self, target_note, detected_frequency, cents_off, confidence):
        if target_note is None:
            return False

        if self.scored_note == target_note.note:
            return False

        if abs(cents_off) > NOTE_HIT_CENTS:
            return False

        points = NOTE_POINTS
        points = points + int(max(0.0, 1.0 - abs(cents_off) / NOTE_HIT_CENTS) * 25.0)
        points = points + int(confidence * 10.0)
        points = points + (self.combo * 5)

        self.score += points
        self.hits += 1
        self.combo += 1
        self.scored_note = target_note.note
        self.missed_note = None
        return True

    def mark_miss(self, target_note):
        if target_note is None:
            return False

        if self.scored_note == target_note.note:
            return False

        if self.missed_note == target_note.note:
            return False

        self.misses += 1
        self.combo = 0
        self.missed_note = target_note.note
        return True


class GameState:
    def __init__(self, song):
        self.song = song
        self.score_state = ScoreState()
        self.pitch_tracker = PitchTracker()
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.latest_frequency = 0.0
        self.latest_rms = 0.0
        self.latest_confidence = 0.0
        self.active_note = None
        self.upcoming_note = None
        self.finished = False

    def update_from_audio(self, frequency_hz, rms):
        stable_frequency, confidence = self.pitch_tracker.update(frequency_hz)
        now = time.time()
        elapsed = now - self.start_time
        active_note, upcoming_note = find_notes_for_time(self.song, elapsed)

        with self.lock:
            self.latest_frequency = stable_frequency
            self.latest_rms = rms
            self.latest_confidence = confidence
            self.active_note = active_note
            self.upcoming_note = upcoming_note

            if active_note is not None:
                self.score_state.reset_note_state(active_note.note)

                if stable_frequency > 0.0:
                    cents_off = cents_difference(stable_frequency, active_note.frequency_hz)
                    self.score_state.award_hit(active_note, stable_frequency, cents_off, confidence)

                if elapsed >= active_note.end_time and self.score_state.scored_note != active_note.note:
                    self.score_state.mark_miss(active_note)

            if elapsed >= self.song.duration() and active_note is None and upcoming_note is None:
                self.finished = True

    def snapshot(self):
        with self.lock:
            return {
                "score": self.score_state.score,
                "hits": self.score_state.hits,
                "misses": self.score_state.misses,
                "combo": self.score_state.combo,
                "frequency": self.latest_frequency,
                "rms": self.latest_rms,
                "confidence": self.latest_confidence,
                "active_note": self.active_note,
                "upcoming_note": self.upcoming_note,
                "finished": self.finished,
            }


def find_notes_for_time(song, elapsed_seconds):
    active_note = None
    upcoming_note = None
    for event in song.note_events:
        if event.start_time <= elapsed_seconds < event.end_time:
            active_note = event
            break
        if event.start_time > elapsed_seconds:
            upcoming_note = event
            break
    return active_note, upcoming_note


def note_to_y_position(note_number, lane_bottom, lane_height):
    min_note = 48
    max_note = 84
    if note_number < min_note:
        note_number = min_note
    if note_number > max_note:
        note_number = max_note

    note_range = max_note - min_note
    if note_range <= 0:
        return lane_bottom + lane_height / 2.0

    ratio = (note_number - min_note) / note_range
    return lane_bottom + (ratio * lane_height)


def time_to_x_position(song, seconds_from_start, track_left, track_width):
    song_duration = song.duration()
    if song_duration <= 0.0:
        return track_left
    ratio = seconds_from_start / song_duration
    return track_left + (ratio * track_width)


def run_game(song, input_device=None):
    import sounddevice as sd
    import pyglet

    selected_device = choose_input_device(input_device)
    game_state = GameState(song)

    window = pyglet.window.Window(
        width=GAME_WINDOW_WIDTH,
        height=GAME_WINDOW_HEIGHT,
        caption="Karaoke Game",
        resizable=True,
    )

    instruction_label = pyglet.text.Label(
        "Sing or whistle the highlighted note",
        x=20,
        y=window.height - 30,
        anchor_x="left",
        anchor_y="center",
        font_size=16,
        color=(255, 255, 255, 255),
    )
    score_label = pyglet.text.Label("", x=20, y=window.height - 60, anchor_x="left", anchor_y="center", font_size=14, color=(255, 255, 255, 255))
    freq_label = pyglet.text.Label("", x=20, y=window.height - 85, anchor_x="left", anchor_y="center", font_size=14, color=(255, 255, 255, 255))
    target_label = pyglet.text.Label("", x=20, y=window.height - 110, anchor_x="left", anchor_y="center", font_size=14, color=(255, 255, 255, 255))
    status_label = pyglet.text.Label("", x=20, y=20, anchor_x="left", anchor_y="bottom", font_size=14, color=(255, 220, 180, 255))

    # audio callback to save data
    def audio_callback(indata, frames, time_info, status):
        if status:
            print(status)

        data = indata[:, 0]  # mono
        freq, rms = detect_major_frequency(data)
        game_state.update_from_audio(freq, rms)

    # open audio input stream
    stream = sd.InputStream(
        device=selected_device,
        channels=CHANNELS,
        samplerate=RATE,
        blocksize=CHUNK_SIZE,
        callback=audio_callback,
        latency="low",
    )

    def draw_song_track(snapshot):
        track_left = 180
        track_right = window.width - 40
        track_bottom = 120
        track_top = window.height - 160
        track_width = track_right - track_left
        track_height = track_top - track_bottom

        background = pyglet.shapes.Rectangle(track_left, track_bottom, track_width, track_height, color=(30, 30, 45))
        background.opacity = 220
        background.draw()

        timeline = pyglet.shapes.Line(track_left, track_bottom + 10, track_right, track_bottom + 10, color=(80, 80, 120))
        timeline.width = 2
        timeline.draw()

        elapsed = time.time() - game_state.start_time
        left_time = elapsed - SONG_LOOKBACK_SECONDS
        right_time = elapsed + SONG_LOOKAHEAD_SECONDS
        visible_span = right_time - left_time

        for event in song.note_events:
            if event.end_time < left_time:
                continue
            if event.start_time > right_time:
                continue

            start_ratio = (event.start_time - left_time) / visible_span
            end_ratio = (event.end_time - left_time) / visible_span
            x1 = track_left + (start_ratio * track_width)
            x2 = track_left + (end_ratio * track_width)
            if x2 < x1:
                x2 = x1 + 2

            y = note_to_y_position(event.note, track_bottom + 20, track_height - 40)
            block_height = 18

            if snapshot["active_note"] is not None and event.note == snapshot["active_note"].note:
                color = (80, 200, 120)
            elif snapshot["upcoming_note"] is not None and event.note == snapshot["upcoming_note"].note:
                color = (220, 180, 80)
            else:
                color = (110, 130, 170)

            note_block = pyglet.shapes.Rectangle(x1, y - block_height / 2.0, x2 - x1, block_height, color=color)
            note_block.opacity = 210
            note_block.draw()

        cursor_x = time_to_x_position(song, elapsed, track_left, track_width)
        cursor = pyglet.shapes.Line(cursor_x, track_bottom, cursor_x, track_top, color=(240, 240, 255))
        cursor.width = 3
        cursor.draw()

    def update_labels(snapshot):
        active_note = snapshot["active_note"]
        upcoming_note = snapshot["upcoming_note"]

        score_label.text = f"Score: {snapshot['score']}   Combo: {snapshot['combo']}   Hits: {snapshot['hits']}   Misses: {snapshot['misses']}"
        if snapshot["frequency"] > 0.0:
            freq_label.text = f"Detected: {snapshot['frequency']:.2f} Hz   RMS: {snapshot['rms']:.4f}   Confidence: {snapshot['confidence']:.2f}"
        else:
            freq_label.text = f"Detected: ---   RMS: {snapshot['rms']:.4f}"

        if active_note is not None:
            target_label.text = f"Target: {note_name(active_note.note)}   {active_note.frequency_hz:.2f} Hz"
        elif upcoming_note is not None:
            target_label.text = f"Next: {note_name(upcoming_note.note)}   {upcoming_note.frequency_hz:.2f} Hz"
        else:
            target_label.text = "Target: ---"

        if snapshot["finished"]:
            status_label.text = "Song finished"
        else:
            status_label.text = ""

    @window.event
    def on_draw():
        window.clear()
        pyglet.gl.glClearColor(0.07, 0.07, 0.12, 1.0)

        snapshot = game_state.snapshot()
        instruction_label.y = window.height - 30
        score_label.y = window.height - 60
        freq_label.y = window.height - 85
        target_label.y = window.height - 110
        update_labels(snapshot)
        draw_song_track(snapshot)

        instruction_label.draw()
        score_label.draw()
        freq_label.draw()
        target_label.draw()
        status_label.draw()

    def update(dt):
        if game_state.snapshot()["finished"]:
            pyglet.app.exit()

    pyglet.clock.schedule_interval(update, 1.0 / 60.0)

    with stream:
        print("Starting karaoke game...")
        print("Close the window or press Ctrl+C to stop.")
        pyglet.app.run()


def detect_major_frequency(data):
    # keep noise from triggering random peaks
    rms = math.sqrt(np.mean(data * data))
    if rms < MIN_RMS:
        return 0.0, rms

    # window before FFT for cleaner peaks
    window = np.hanning(len(data))
    spectrum = np.fft.rfft(data * window)
    magnitudes = np.abs(spectrum)
    freqs = np.fft.rfftfreq(len(data), d=1.0 / RATE)

    if len(magnitudes) == 0:
        return 0.0, rms

    magnitudes[0] = 0.0
    valid = (freqs >= MIN_FREQ) & (freqs <= MAX_FREQ)
    if not np.any(valid):
        return 0.0, rms

    valid_indices = np.where(valid)[0]
    best_local_index = int(np.argmax(magnitudes[valid]))
    best_index = int(valid_indices[best_local_index])
    major_frequency = float(freqs[best_index])

    return major_frequency, rms


def choose_input_device(default_device=None):
    import sounddevice as sd

    # print info about audio devices
    print("Available input devices:\n")
    devices = sd.query_devices()

    input_devices = []
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            print(f"{i}: {dev['name']}")
            input_devices.append(i)

    if default_device is not None:
        return default_device

    user_text = input("\nSelect input device (Enter for default): ").strip()
    if user_text == "":
        return None

    try:
        selected_device = int(user_text)
    except ValueError:
        print("Invalid selection. Using default input device.")
        return None

    if selected_device not in input_devices:
        print("Selected device is not a valid input. Using default input device.")
        return None

    return selected_device


def listen_for_frequency(song, input_device=None):
    import sounddevice as sd

    selected_device = choose_input_device(input_device)
    last_print_time = [0.0]
    pitch_tracker = PitchTracker()
    score_state = ScoreState()
    start_time = time.time()
    last_seen_target_note = [None]

    # audio callback to save data
    def audio_callback(indata, frames, time_info, status):
        if status:
            print(status)

        data = indata[:, 0]  # mono
        freq, rms = detect_major_frequency(data)
        stable_freq, confidence = pitch_tracker.update(freq)

        now = time.time()
        elapsed = now - start_time
        active_note, upcoming_note = find_notes_for_time(song, elapsed)

        if active_note is not None:
            score_state.reset_note_state(active_note.note)

            if last_seen_target_note[0] != active_note.note:
                last_seen_target_note[0] = active_note.note

            if stable_freq > 0.0:
                cents_off = cents_difference(stable_freq, active_note.frequency_hz)
                score_state.award_hit(active_note, stable_freq, cents_off, confidence)

            if elapsed >= active_note.end_time and score_state.scored_note != active_note.note:
                score_state.mark_miss(active_note)

        if now - last_print_time[0] >= 0.1:
            display_note = active_note
            if display_note is None:
                display_note = upcoming_note

            if display_note is None:
                target_text = "Target: ---"
            else:
                target_text = f"Target: {note_name(display_note.note)} {display_note.frequency_hz:7.2f} Hz"

            if stable_freq > 0.0 and active_note is not None:
                cents_off = 0.0
                cents_off = cents_difference(stable_freq, active_note.frequency_hz)
                print(
                    f"\rDetected frequency: {stable_freq:7.2f} Hz  "
                    f"RMS: {rms:0.4f}  Confidence: {confidence:0.2f}  "
                    f"{target_text}  Score: {score_state.score}  Combo: {score_state.combo}  "
                    f"Hits: {score_state.hits}  Misses: {score_state.misses}  Cents: {cents_off:0.1f}",
                    end="",
                    flush=True,
                )
            else:
                print(
                    f"\rDetected frequency:   ---    Hz  RMS too low  {target_text}  "
                    f"Score: {score_state.score}  Combo: {score_state.combo}  Hits: {score_state.hits}  Misses: {score_state.misses}",
                    end="",
                    flush=True,
                )
            last_print_time[0] = now

    # open audio input stream
    stream = sd.InputStream(
        device=selected_device,
        channels=CHANNELS,
        samplerate=RATE,
        blocksize=CHUNK_SIZE,
        callback=audio_callback,
        latency="low",
    )

    # continuously capture and detect
    with stream:
        print("\nStreaming... (Ctrl+C to stop)")
        try:
            while True:
                sd.sleep(200)
        except KeyboardInterrupt:
            print("\nStopped listening.")


def build_argument_parser():
    parser = argparse.ArgumentParser(description="Load a MIDI file and print its note timeline.")
    parser.add_argument("midi_file", help="Path to the MIDI file to load")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of note events to print",
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Start live microphone frequency detection after loading the MIDI file",
    )
    parser.add_argument(
        "--game",
        action="store_true",
        help="Start the pyglet karaoke window",
    )
    parser.add_argument(
        "--input-device",
        type=int,
        default=None,
        help="Optional input device id to skip interactive selection",
    )
    return parser


def main(argv=None):
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    song = load_song(args.midi_file)

    print(f"Midi File: {song.source_path}")
    print(f"Ticks per beat: {song.ticks_per_beat}")
    print(f"Note events: {len(song.note_events)}")
    song_duration = song.duration()
    print(f"Duration: {song_duration:.3f}s")

    limit = args.limit
    if limit < 0:
        limit = 0
    
    for i in range(min(limit, len(song.note_events))):
        event = song.note_events[i]
        print(format_note_event(event))

    if args.game:
        try:
            run_game(song, args.input_device)
        except ImportError:
            print("sounddevice or pyglet is not installed. Install both to use --game.")
            return 1

    if args.listen:
        try:
            listen_for_frequency(song, args.input_device)
        except ImportError:
            print("sounddevice is not installed. Install it to use --listen.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())