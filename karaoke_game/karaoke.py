import argparse

from audio import listen_for_frequency
from game import run_game
from midi_loader import format_event, load_song


def build_argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('midi_file')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--listen', action='store_true')
    parser.add_argument('--game', action='store_true')
    parser.add_argument('--play-midi', action='store_true')
    parser.add_argument('--input-device', type=int, default=None)
    return parser


def main(argv=None):
    args = build_argument_parser().parse_args(argv)
    try:
        song = load_song(args.midi_file)
    except Exception as exc:
        print('Error loading MIDI:', exc)
        return 1

    print('Loaded', song.source_path, 'events=', len(song.note_events), 'dur=', f"{song.duration():.3f}")
    for event in song.note_events[:args.limit]:
        print(format_event(event))

    if args.listen:
        listen_for_frequency(song, input_device=args.input_device)
    if args.game:
        run_game(song, input_device=args.input_device, play_midi=args.play_midi)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
