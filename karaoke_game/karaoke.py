import os
import sys
import sounddevice as sd

from game import run_game
from midi_loader import load_song


# CLI entrypoint: choose MIDI file and input device, then launch the game
def main():
    base_dir = os.path.join('read_midi')
    if len(sys.argv) < 2:
        user_input = input(f"Enter MIDI file name: ").strip() 
    else:
        user_input = sys.argv[1].strip()

    # normalize input: empty -> default berge.mid
    if not user_input:
        midi_file = os.path.join(base_dir, 'berge.mid')
    else:
        # if user provided a bare name, ensure extension
        if not user_input.lower().endswith('.mid'):
            user_input = user_input + '.mid'
        # if path is not absolute and doesn't start with base_dir, prefix base_dir
        if not os.path.isabs(user_input) and not (user_input.startswith(base_dir + os.sep) or user_input.startswith(base_dir + '/')):
            midi_file = os.path.join(base_dir, user_input)
        else:
            midi_file = user_input

    try:
        song = load_song(midi_file)
    except Exception as exc:
        print('Error loading MIDI:', exc)
        return 1

    print(f"\nLoaded {song.source_path} with {len(song.note_events)} events, duration: {song.duration():.3f}s\n")

    print("Available input devices:\n")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"{i}: {device['name']}")

    try:
        device_id = int(input("\nSelect input device: ").strip())
    except ValueError:
        device_id = None

    run_game(song, input_device=device_id, play_midi=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
