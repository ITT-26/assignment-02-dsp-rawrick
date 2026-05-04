import sounddevice as sd

from whistle_detector import BLOCK_SIZE, SAMPLE_RATE, WhistleDetector


def print_input_devices():
    print("Available input devices:\n")
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0:
            print(f"{index}: {device['name']}")


def main():
    print_input_devices()
    device = int(input("\nSelect input device: "))

    detector = WhistleDetector()

    def audio_callback(indata, frames, time, status):
        if status:
            print(status)

        samples = indata[:, 0]
        direction = detector.process(samples)
        if direction == "up":
            print("Upward whistle detected")
        elif direction == "down":
            print("Downward whistle detected")

    stream = sd.InputStream(
        device=device,
        channels=1,
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        callback=audio_callback,
        latency="low",
    )

    with stream:
        print("\nListening for whistle chirps... (Ctrl+C to stop)")
        try:
            while True:
                sd.sleep(1000)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
