import mido


# single note event with cached frequency
class NoteEvent:
    def __init__(self, note, start_time, end_time, velocity):
        self.note = note
        self.frequency_hz = 440.0 * 2 ** ((note - 69) / 12.0)
        self.start_time = start_time
        self.end_time = end_time
        self.velocity = velocity


# container for song metadata and note events
class SongData:
    def __init__(self, source_path, ticks_per_beat, note_events):
        self.source_path = source_path
        self.ticks_per_beat = ticks_per_beat
        self.note_events = note_events

    # total duration in seconds
    def duration(self):
        return max((event.end_time for event in self.note_events), default=0.0)


# parse a MIDI file and return SongData
def load_song(path):
    midi = mido.MidiFile(path)
    current_time = 0.0
    tempo = 500000
    open_notes = {}
    events = []

    for message in mido.merge_tracks(midi.tracks):
        current_time += mido.tick2second(message.time, midi.ticks_per_beat, tempo)
        if message.type == 'set_tempo':
            tempo = message.tempo
        elif message.type == 'note_on' and message.velocity > 0:
            open_notes.setdefault(message.note, []).append((current_time, message.velocity))
        elif message.type in ('note_off', 'note_on'):
            stack = open_notes.get(message.note)
            if stack:
                start_time, velocity = stack.pop()
                events.append(NoteEvent(message.note, start_time, current_time, velocity))

    for note, stack in open_notes.items():
        while stack:
            start_time, velocity = stack.pop()
            events.append(NoteEvent(note, start_time, current_time, velocity))

    events.sort(key=lambda event: (event.start_time, event.note, event.end_time))
    return SongData(path, midi.ticks_per_beat, events)


# helper to format a note event for logging
def format_event(event):
    return f"note={event.note} freq={event.frequency_hz:.2f}Hz start={event.start_time:.3f}s end={event.end_time:.3f}s dur={event.end_time - event.start_time:.3f}s vel={event.velocity}"
