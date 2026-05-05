from pynput.keyboard import Controller, Key
import sounddevice as sd

from whistle_input import WhistleDetector, open_input_stream


def main():
    # choose input device
    print('Available input devices:\n')
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            print(f"{i}: {dev['name']}")
    try:
        value = input('\nSelect input device (Enter for default): ').strip()
        device = None if value == '' else int(value)
    except Exception:
        device = None

    keyboard = Controller()
    detector = WhistleDetector()

    # turn whistle directions into arrow key presses
    def on_dir(d):
        if d == 'up':
            keyboard.press(Key.up)
            keyboard.release(Key.up)
        elif d == 'down':
            keyboard.press(Key.down)
            keyboard.release(Key.down)

    stream = open_input_stream(detector, on_dir, device=device)

    print('\nListening for whistles')
    try:
        with stream:
            while True:
                sd.sleep(1000)
    except KeyboardInterrupt:
        print('\nStopped')


if __name__ == '__main__':
    main()