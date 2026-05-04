import argparse
import math
import mido


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


def build_argument_parser():
    parser = argparse.ArgumentParser(description="Load a MIDI file and print its note timeline.")
    parser.add_argument("midi_file", help="Path to the MIDI file to load")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of note events to print",
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())