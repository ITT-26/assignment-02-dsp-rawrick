import argparse
import math
import time

import mido
import numpy as np


# audio settings (kept close to audio_sample.py)
CHUNK_SIZE = 1024
RATE = 44100
CHANNELS = 1
MIN_RMS = 0.01
MIN_FREQ = 70.0
MAX_FREQ = 1200.0


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


def listen_for_frequency(input_device=None):
    import sounddevice as sd

    selected_device = choose_input_device(input_device)
    last_print_time = [0.0]

    # audio callback to save data
    def audio_callback(indata, frames, time_info, status):
        if status:
            print(status)

        data = indata[:, 0]  # mono
        freq, rms = detect_major_frequency(data)

        now = time.time()
        if now - last_print_time[0] >= 0.1:
            if freq > 0.0:
                print(f"\rDetected frequency: {freq:7.2f} Hz  RMS: {rms:0.4f}", end="", flush=True)
            else:
                print("\rDetected frequency:   ---    Hz  RMS too low", end="", flush=True)
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

    if args.listen:
        try:
            listen_for_frequency(args.input_device)
        except ImportError:
            print("sounddevice is not installed. Install it to use --listen.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())