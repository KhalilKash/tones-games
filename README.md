# Tones Games

A pitch training game: listen to a sequence, then identify each tone in order.

Play online: https://khalilkash.github.io/tones-games/

## Web version

Open `index.html` in a browser. No installation or build is needed. Audio starts after you click a tone or begin a test.

- Choose between 1 and 15 playable tones.
- Start a quick test of 1–5 notes, or set a custom length of up to 100 notes.
- Replay a sequence and check your answers.

GitHub Pages serves the root of the `main` branch. Push changes to `index.html` to update the website.

## Desktop version

The folder also includes a Python version for macOS. It requires Python with Tkinter and uses macOS's built-in `afplay` for audio:

```sh
python3 pitch_trainer-2.py
```
