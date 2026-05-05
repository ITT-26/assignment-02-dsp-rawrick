import pyglet
import sounddevice as sd

from whistle_input import WhistleDetector, open_input_stream


# show a stack of rectangles and move the selected one
def run_game(direction):
    boxes = 3
    selected = [boxes // 2]

    window = pyglet.window.Window(640, 520, caption='Whistle Input Game', resizable=True)
    title = pyglet.text.Label('Whistle Game', x=window.width // 2, y=window.height - 28, anchor_x='center', anchor_y='center')
    hint = pyglet.text.Label('Whistle up / down to move the selection', x=window.width // 2, y=24, anchor_x='center', anchor_y='center', font_size=12)

    # check the shared value and update the selection
    def tick(dt):
        value = direction[0]
        if value == 'up' and selected[0] > 0:
            selected[0] -= 1
        elif value == 'down' and selected[0] < boxes - 1:
            selected[0] += 1

        if value is not None:
            direction[0] = None

    @window.event
    def on_draw():
        window.clear()
        title.x = window.width // 2
        hint.x = window.width // 2
        title.draw()
        hint.draw()

        box_width = min(260, window.width - 120)
        box_height = 44
        gap = 12
        total_height = boxes * box_height + (boxes - 1) * gap
        top = window.height / 2 + total_height / 2
        left = (window.width - box_width) / 2

        # draw the rectangle stack
        for index in range(boxes):
            y = top - (index + 1) * box_height - index * gap
            color = (240, 180, 70) if index == selected[0] else (70, 90, 120)
            pyglet.shapes.Rectangle(left, y, box_width, box_height, color=color).draw()

    @window.event
    def on_key_press(symbol, modifiers):
        if symbol == pyglet.window.key.Q:
            pyglet.app.exit()

    pyglet.clock.schedule_interval(tick, 1 / 30.0)
    pyglet.app.run()


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

    detector = WhistleDetector()
    direction = [None]

    def on_dir(d):
        direction[0] = d

    stream = open_input_stream(detector, on_dir, device=device)

    with stream:
        run_game(direction)


if __name__ == '__main__':
    main()