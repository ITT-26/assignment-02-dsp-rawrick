[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/B3oR_XLF)
# Karaoke and Whistleboard
## Quickstart
1. Create a Virtual Environment (recommended)
2. Install required packages
```
pip install -r requirements.txt
```
3. Run either `python karaoke_game/karaoke.py` (1), `python whistle_input/game.py` (2a) or `python whistle_input/whistleboard.py` (2b)
## Instructions
### Karaoke Game
When starting the program you are prompted to enter a MIDI file's name. The file has to be located inside the `/read_midi` folder. Next select your input device from the list of available devices on your system and enter the corresponding number. This will start the game where now you can score points by hitting the right notes. When the song has finished you can see your score (including combos) and overall accuracy. Finally you can choose to restart or quit the game.
### Whistle Input
1. Part one of the whistle program is a simple game that uses up and downwards whistles to select a rectangle. Simply select an input device and start whistling. Short whistles tend to work better.
2. The so called Whistleboard is a program that triggers up- and down keypresses on whistle. Again select an input device when running the script and start whistling while inside a Code Editor for example.
## AI usage
The following AI models were used for autcomplete-suggestions, debugging help and final refactoring/clean-up
- Claude Haiku 4.5
- GPT-5.3-Codex
- GPT-5.4-mini