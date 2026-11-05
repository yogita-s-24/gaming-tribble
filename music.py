"""
Background music for Tribble Run.

If a file named music.ogg / music.mp3 / music.wav exists in the assets/ folder next to this
script, it is streamed and looped. Otherwise an original chiptune loop is synthesized at
startup (square-wave lead, triangle bass, noise drums), so the game needs no audio files.
"""
import array
import io
import math
import os
import random
import sys
import wave

import pygame

SAMPLE_RATE = 22050
BPM = 150
STEP = int(SAMPLE_RATE * 60 / BPM / 2)  # samples per eighth note
VOLUME = 0.5

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
MUSIC_FILES = ("music.ogg", "music.mp3", "music.wav")

# --------------------------------------------------------------------------- the tune
# Notes are MIDI numbers (60 = middle C); None is a rest. Lengths are in eighth notes.
C5, D5, E5, F5, G5, A5, B5 = 72, 74, 76, 77, 79, 81, 83
C6, D6, E6 = 84, 86, 88

MELODY = [
    (E5, 1), (G5, 1), (C6, 2), (G5, 1), (E5, 1), (G5, 2),        # C
    (A5, 1), (C6, 1), (E6, 2), (C6, 1), (A5, 1), (E5, 2),        # Am
    (F5, 1), (A5, 1), (C6, 1), (A5, 1), (F5, 2), (A5, 2),        # F
    (G5, 2), (B5, 1), (D6, 1), (B5, 2), (None, 2),               # G
    (E5, 1), (G5, 1), (C6, 2), (E6, 1), (D6, 1), (C6, 2),        # C
    (C6, 1), (B5, 1), (A5, 2), (E5, 2), (A5, 2),                 # Am
    (A5, 1), (G5, 1), (F5, 2), (D5, 1), (F5, 1), (B5, 2),        # F  G
    (C6, 4), (G5, 2), (None, 2),                                 # C
]

# One chord root per half bar (4 eighths), bass plays root / octave-up eighths.
BASS_ROOTS = [48, 48, 45, 45, 41, 41, 43, 43,
              48, 48, 45, 45, 41, 43, 48, 48]


def _freq(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def _square(note, length, amp=0.16, duty=0.25):
    n = length * STEP
    if note is None:
        return [0.0] * n
    f = _freq(note) / SAMPLE_RATE
    gate = int(n * 0.9)  # small gap so repeated notes are distinct
    out = []
    for i in range(n):
        if i >= gate:
            out.append(0.0)
            continue
        env = amp * (0.55 + 0.45 * math.exp(-i / (STEP * 0.6)))
        out.append(env if (i * f) % 1.0 < duty else -env)
    return out


def _triangle(note, length, amp=0.22):
    n = length * STEP
    f = _freq(note) / SAMPLE_RATE
    gate = int(n * 0.85)
    return [amp * (4 * abs((i * f) % 1.0 - 0.5) - 1) if i < gate else 0.0 for i in range(n)]


def _drums(steps):
    rng = random.Random(7)
    hat_len, kick_len = STEP // 4, STEP
    hat = [rng.uniform(-1, 1) * 0.06 * (1 - i / hat_len) for i in range(hat_len)]
    kick = []
    phase = 0.0
    for i in range(kick_len):  # pitch sweeps down from ~150 Hz to ~45 Hz
        t = i / kick_len
        phase += (45 + 105 * (1 - t) ** 3) / SAMPLE_RATE
        kick.append(0.35 * math.sin(2 * math.pi * phase) * (1 - t) ** 2)
    out = [0.0] * (steps * STEP)
    for s in range(steps):
        start = s * STEP
        sound = kick if s % 4 == 0 else hat
        out[start:start + len(sound)] = sound
    return out


def build_loop():
    lead = []
    for note, length in MELODY:
        lead += _square(note, length)
    bass = []
    for root in BASS_ROOTS:
        for k in range(4):
            bass += _triangle(root + (12 if k % 2 else 0), 1)
    drums = _drums(len(bass) // STEP)
    return [a + b + c for a, b, c in zip(lead, bass, drums)]


def _to_sound(samples):
    """Wrap the samples in an in-memory mono WAV; pygame converts it to the mixer's format."""
    pcm = array.array("h", (int(max(-1.0, min(1.0, s)) * 32767) for s in samples))
    if sys.byteorder == "big":
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    buf.seek(0)
    return pygame.mixer.Sound(file=buf)


# --------------------------------------------------------------------------- player
class Music:
    """Small wrapper so the game can play / pause / stop / mute without caring about the source."""

    def __init__(self):
        self.enabled = False
        self.muted = False
        self.playing = False
        self.file = None
        self.sound = None
        self.channel = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.file = next((os.path.join(ASSET_DIR, name) for name in MUSIC_FILES
                              if os.path.isfile(os.path.join(ASSET_DIR, name))), None)
            if self.file:
                pygame.mixer.music.load(self.file)
                pygame.mixer.music.set_volume(VOLUME)
            else:
                self.sound = _to_sound(build_loop())
                self.sound.set_volume(VOLUME)
                pygame.mixer.set_reserved(1)
                self.channel = pygame.mixer.Channel(0)
            self.enabled = True
        except (pygame.error, OSError) as exc:  # no audio device, bad file, etc.
            print(f"Music disabled: {exc}")

    def play(self):
        """Start the loop from the beginning."""
        if not self.enabled:
            return
        self.playing = True
        if self.file:
            pygame.mixer.music.play(loops=-1)
        else:
            self.channel.play(self.sound, loops=-1)
        self._apply_volume()

    def stop(self):
        if not self.enabled:
            return
        self.playing = False
        if self.file:
            pygame.mixer.music.stop()
        else:
            self.channel.stop()

    def pause(self):
        if self.enabled:
            pygame.mixer.music.pause() if self.file else self.channel.pause()

    def unpause(self):
        if self.enabled:
            pygame.mixer.music.unpause() if self.file else self.channel.unpause()

    def toggle_mute(self):
        self.muted = not self.muted
        self._apply_volume()

    def _apply_volume(self):
        if not self.enabled:
            return
        vol = 0.0 if self.muted else VOLUME
        if self.file:
            pygame.mixer.music.set_volume(vol)
        else:
            self.channel.set_volume(1.0)
            self.sound.set_volume(vol)
