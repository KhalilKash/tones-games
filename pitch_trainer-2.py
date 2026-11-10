#!/usr/bin/env python3
"""Run with python3 pitch_trainer.py on macOS."""

import math
import random
import struct
import subprocess
import tempfile
import tkinter as tk
import wave
from pathlib import Path
from tkinter import ttk


BASE_FREQUENCIES = (261.63, 293.66, 329.63, 392.00, 440.00)  # C4, D4, E4, G4, A4
FREQUENCIES = tuple(
    frequency * multiplier for multiplier in (1, 2, 4) for frequency in BASE_FREQUENCIES
)
DEFAULT_TONE_COUNT = len(BASE_FREQUENCIES)
MAX_PUZZLE_LENGTH = 100
SAMPLE_RATE = 44_100
NOTE_GAP = bytes(2 * int(SAMPLE_RATE * 0.16))
AUDIO_PLAYER = "/usr/bin/afplay"


def make_tone(frequency):
    sample_count = int(SAMPLE_RATE * 0.42)
    fade_samples = int(SAMPLE_RATE * 0.012)
    phase_step = math.tau * frequency / SAMPLE_RATE
    # Fade both ends to avoid clicks as tones start and stop.
    samples = []
    for index in range(sample_count):
        envelope = min(1, index / fade_samples, (sample_count - 1 - index) / fade_samples)
        samples.append(round(9_000 * math.sin(index * phase_step) * envelope))
    return struct.pack(f"<{sample_count}h", *samples)


class PitchTrainer:
    def __init__(self, root, audio_path):
        self.root = root
        self.audio_path = str(audio_path)
        self.tones = tuple(make_tone(frequency) for frequency in FREQUENCIES)
        self.player = None
        self.last_sequence = ()
        self.answer_index = None
        self.tone_count = DEFAULT_TONE_COUNT
        self.length_text = tk.StringVar(root, "6")
        self.status = tk.StringVar(root, "Try a tone or choose a test to begin.")

        root.title("Pitch Trainer")
        panel = ttk.Frame(root, padding=20)
        panel.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        panel.columnconfigure(0, weight=1)

        settings = ttk.Frame(panel)
        settings.grid(row=0, sticky="ew", pady=(0, 12))
        ttk.Label(settings, text="Playable tones").pack(side="left", padx=(0, 8))
        self.tone_count_box = ttk.Combobox(
            settings, values=tuple(range(1, len(self.tones) + 1)), state="readonly", width=4
        )
        self.tone_count_box.pack(side="left")
        self.tone_count_box.bind("<<ComboboxSelected>>", self.apply_tone_count)
        self.controls = [self.tone_count_box]

        ttk.Label(panel, text="Tones · low to high").grid(row=1, sticky="w")
        tone_grid = ttk.Frame(panel)
        tone_grid.grid(row=2, sticky="ew")
        self.tone_buttons = [
            ttk.Button(tone_grid, text=str(note + 1), command=lambda pitch=note: self.choose_tone(pitch))
            for note in range(len(self.tones))
        ]
        self.controls.extend(self.tone_buttons)

        ttk.Label(panel, text="Start a test").grid(row=3, sticky="w", pady=(16, 0))
        test_grid = ttk.Frame(panel)
        test_grid.grid(row=4, sticky="ew")
        for column in range(5):
            tone_grid.columnconfigure(column, weight=1, uniform="tones")
            test_grid.columnconfigure(column, weight=1, uniform="tests")
            length = column + 1
            test_label = "1 note" if length == 1 else f"{length} notes"
            test_button = ttk.Button(
                test_grid, text=test_label, command=lambda count=length: self.start_test(count)
            )
            test_button.grid(row=0, column=column, sticky="ew", padx=2, pady=(5, 0))
            self.controls.append(test_button)

        custom = ttk.Frame(panel)
        custom.grid(row=5, sticky="ew", pady=(10, 0))
        ttk.Label(custom, text=f"Custom length (1–{MAX_PUZZLE_LENGTH})").pack(side="left", padx=(0, 8))
        length_box = ttk.Spinbox(
            custom, from_=1, to=MAX_PUZZLE_LENGTH, width=4, textvariable=self.length_text
        )
        length_box.pack(side="left")
        length_box.bind("<Return>", lambda event: self.start_custom_test())
        custom_button = ttk.Button(custom, text="Start", command=self.start_custom_test)
        custom_button.pack(side="left", padx=(6, 0))
        self.controls.extend((length_box, custom_button))
        self.replay_button = ttk.Button(custom, text="Replay sequence", command=self.replay_sequence)
        self.replay_button.pack(side="right", padx=(12, 0))

        ttk.Separator(panel).grid(row=6, sticky="ew", pady=(16, 12))
        ttk.Label(panel, textvariable=self.status, wraplength=450).grid(row=7, sticky="w")
        self.show_tones(self.tone_count)
        self.update_controls()
        root.update_idletasks()
        root.minsize(root.winfo_reqwidth(), root.winfo_reqheight() + 20)

    def show_tones(self, count):
        self.tone_count = count
        self.tone_count_box.current(count - 1)
        for note, button in enumerate(self.tone_buttons):
            if note < count:
                row, column = divmod(note, 5)
                button.grid(row=row, column=column, sticky="ew", padx=2, pady=(5, 0))
            else:
                button.grid_remove()

    def apply_tone_count(self, _event):
        if self.player is not None:
            return
        count = self.tone_count_box.current() + 1
        if count != self.tone_count:
            self.show_tones(count)
            self.end_test(f"Playable tone count set to {count}. Choose a test to begin.")

    def start_custom_test(self):
        if self.player is not None:
            return
        try:
            length = int(self.length_text.get())
        except ValueError:
            length = 0
        if not 1 <= length <= MAX_PUZZLE_LENGTH:
            self.status.set(f"Custom length must be a whole number from 1 to {MAX_PUZZLE_LENGTH}.")
            return
        self.start_test(length)

    def start_test(self, length):
        if self.player is not None:
            return
        self.last_sequence = tuple(random.choices(range(self.tone_count), k=length))
        self.replay_sequence()

    def replay_sequence(self):
        if self.player is not None or not self.last_sequence:
            return
        needed_tones = max(self.last_sequence) + 1
        if needed_tones > self.tone_count:
            self.show_tones(needed_tones)
        self.answer_index = 0
        self.status.set("Listen to the sequence…")
        self.play(self.last_sequence)

    def choose_tone(self, note):
        if self.player is not None or note >= self.tone_count:
            return
        if self.answer_index is None:
            self.play((note,))
            return
        expected = self.last_sequence[self.answer_index]
        if note != expected:
            correct_sequence = " → ".join(str(pitch + 1) for pitch in self.last_sequence)
            self.end_test(
                f"Incorrect on note {self.answer_index + 1} of {len(self.last_sequence)}. "
                f"You chose tone {note + 1}. The correct tone was {expected + 1}.\n"
                f"Correct sequence\n{correct_sequence}"
            )
            return

        self.answer_index += 1
        if self.answer_index == len(self.last_sequence):
            self.end_test("Correct! Replay this sequence or choose another test.")
        else:
            self.prompt_for_note()

    def end_test(self, message):
        self.answer_index = None
        self.status.set(message)

    def prompt_for_note(self):
        self.status.set(
            f"Note {self.answer_index + 1} of {len(self.last_sequence)}. Click the matching tone."
        )

    def update_controls(self):
        playing = self.player is not None
        for control in self.controls:
            control.state(["disabled"] if playing else ["!disabled"])
        self.replay_button.state(["disabled"] if playing or not self.last_sequence else ["!disabled"])

    def play(self, notes):
        try:
            with wave.open(self.audio_path, "wb") as wav:
                wav.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
                wav.writeframes(NOTE_GAP.join(self.tones[note] for note in notes))
            self.player = subprocess.Popen(
                [AUDIO_PLAYER, self.audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except OSError:
            self.end_test("Audio playback failed. This app uses macOS’s afplay.")
            self.update_controls()
            return

        self.update_controls()
        self.root.after(25, self.check_playback)

    def check_playback(self):
        exit_code = self.player.poll()
        if exit_code is None:
            self.root.after(25, self.check_playback)
            return

        self.player = None
        self.update_controls()
        if exit_code != 0:
            self.end_test("Audio playback failed. Replay the sequence or choose a test.")
        elif self.answer_index is not None:
            self.prompt_for_note()

    def stop_playback(self):
        if self.player is not None:
            self.player.terminate()
            try:
                self.player.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.player.kill()
                self.player.wait()


def main():
    with tempfile.TemporaryDirectory(prefix="pitch-trainer-") as directory:
        root = tk.Tk()
        app = PitchTrainer(root, Path(directory) / "tones.wav")
        try:
            root.mainloop()
        finally:
            app.stop_playback()


if __name__ == "__main__":
    main()
