"""Sound manager for the draughts application.

Generates WAV sound effects programmatically and plays them via
QMediaPlayer (PyQt6.QtMultimedia).  Falls back silently when the
multimedia module is unavailable.
"""

from __future__ import annotations

import atexit
import math
import os
import random
import shutil
import struct
import tempfile
import wave

# ---------------------------------------------------------------------------
# Try to import PyQt6 multimedia; flag availability
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtCore import QUrl
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    _HAS_MULTIMEDIA = True
except ImportError:
    _HAS_MULTIMEDIA = False


# ---------------------------------------------------------------------------
# WAV-generation helpers
# ---------------------------------------------------------------------------
_SAMPLE_RATE = 44100
_MAX_AMP = 32767  # 16-bit signed max


def _pack_samples(samples: list[float]) -> bytes:
    """Pack a list of float samples (-1..1) into 16-bit LE PCM bytes."""
    data = b""
    for s in samples:
        clamped = max(-1.0, min(1.0, s))
        data += struct.pack("<h", int(clamped * _MAX_AMP))
    return data


def _write_wav(path: str, samples: list[float]) -> None:
    """Write float samples (-1..1) as a 16-bit mono WAV file."""
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(_pack_samples(samples))


def _sine(freq: float, duration: float, volume: float = 1.0,
          phase: float = 0.0) -> list[float]:
    """Generate a sine-wave tone."""
    n = int(_SAMPLE_RATE * duration)
    return [
        volume * math.sin(2.0 * math.pi * freq * i / _SAMPLE_RATE + phase)
        for i in range(n)
    ]


def _fade(samples: list[float], fade_in: float = 0.0,
          fade_out: float = 0.0) -> list[float]:
    """Apply linear fade-in / fade-out to avoid clicks."""
    n = len(samples)
    fi = int(_SAMPLE_RATE * fade_in)
    fo = int(_SAMPLE_RATE * fade_out)
    out = list(samples)
    for i in range(min(fi, n)):
        out[i] *= i / fi
    for i in range(min(fo, n)):
        out[n - 1 - i] *= i / fo
    return out


def _envelope_exp(samples: list[float], decay: float) -> list[float]:
    """Apply exponential decay envelope.  decay is the time constant in seconds."""
    n = len(samples)
    return [
        s * math.exp(-i / (_SAMPLE_RATE * decay))
        for i, s in enumerate(samples)
    ]


def _mix(*tracks: list[float]) -> list[float]:
    """Mix multiple tracks (same or different lengths) by summing."""
    length = max(len(t) for t in tracks)
    out = [0.0] * length
    for t in tracks:
        for i, s in enumerate(t):
            out[i] += s
    return out


def _normalize(samples: list[float], peak: float = 0.9) -> list[float]:
    """Normalize to given peak amplitude."""
    mx = max(abs(s) for s in samples) if samples else 1.0
    if mx < 1e-9:
        return samples
    factor = peak / mx
    return [s * factor for s in samples]


def _noise(duration: float, volume: float = 1.0) -> list[float]:
    """White noise."""
    n = int(_SAMPLE_RATE * duration)
    return [volume * (random.random() * 2.0 - 1.0) for _ in range(n)]


def _bandpass_simple(samples: list[float], center: float,
                     bandwidth: float) -> list[float]:
    """Very simple resonant band-pass via biquad filter."""
    omega = 2.0 * math.pi * center / _SAMPLE_RATE
    alpha = math.sin(omega) * math.sinh(
        math.log(2.0) / 2.0 * bandwidth * omega / math.sin(omega)
    ) if abs(math.sin(omega)) > 1e-9 else 0.01
    b0 = alpha
    b1 = 0.0
    b2 = -alpha
    a0 = 1.0 + alpha
    a1 = -2.0 * math.cos(omega)
    a2 = 1.0 - alpha
    # Normalize
    b0 /= a0; b1 /= a0; b2 /= a0
    a1 /= a0; a2 /= a0
    out = [0.0] * len(samples)
    x1 = x2 = y1 = y2 = 0.0
    for i, x0 in enumerate(samples):
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out[i] = y0
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return out


def _lowpass_simple(samples: list[float], cutoff: float) -> list[float]:
    """Simple one-pole low-pass filter."""
    rc = 1.0 / (2.0 * math.pi * cutoff)
    dt = 1.0 / _SAMPLE_RATE
    alpha = dt / (rc + dt)
    out = [0.0] * len(samples)
    prev = 0.0
    for i, s in enumerate(samples):
        prev = prev + alpha * (s - prev)
        out[i] = prev
    return out


def _freq_sweep(f_start: float, f_end: float, duration: float,
                volume: float = 1.0) -> list[float]:
    """Linear frequency sweep (chirp)."""
    n = int(_SAMPLE_RATE * duration)
    out = []
    for i in range(n):
        t = i / _SAMPLE_RATE
        frac = t / duration
        freq = f_start + (f_end - f_start) * frac
        phase = 2.0 * math.pi * (f_start * t + 0.5 * (f_end - f_start) * t * t / duration)
        out.append(volume * math.sin(phase))
    return out


def _silence(duration: float) -> list[float]:
    return [0.0] * int(_SAMPLE_RATE * duration)


def _concat(*tracks: list[float]) -> list[float]:
    out: list[float] = []
    for t in tracks:
        out.extend(t)
    return out


# ---------------------------------------------------------------------------
# Sound generation functions
# ---------------------------------------------------------------------------

def _gen_piece_move() -> list[float]:
    """Soft click/tap — short filtered noise burst + quiet high sine tap."""
    burst = _noise(0.015, 0.6)
    burst = _bandpass_simple(burst, 3000.0, 1.5)
    burst = _envelope_exp(burst, 0.006)
    tap = _sine(1800.0, 0.012, 0.2)
    tap = _envelope_exp(tap, 0.005)
    samples = _mix(burst, tap)
    samples = _fade(samples, 0.001, 0.005)
    return _normalize(samples, 0.5)


def _gen_piece_capture() -> list[float]:
    """Louder impact — low thud + mid crack."""
    thud = _sine(120.0, 0.1, 0.8)
    thud = _envelope_exp(thud, 0.04)
    crack = _noise(0.03, 1.0)
    crack = _bandpass_simple(crack, 2000.0, 1.2)
    crack = _envelope_exp(crack, 0.012)
    # Short mid-tone
    mid = _sine(400.0, 0.06, 0.4)
    mid = _envelope_exp(mid, 0.025)
    samples = _mix(thud, crack, mid)
    samples = _fade(samples, 0.001, 0.01)
    return _normalize(samples, 0.7)


def _gen_piece_king() -> list[float]:
    """Ascending triumphant tone — arpeggiated major chord."""
    notes = [523.25, 659.25, 783.99, 1046.50]  # C5, E5, G5, C6
    parts: list[list[float]] = []
    for idx, freq in enumerate(notes):
        delay = _silence(idx * 0.07)
        tone = _sine(freq, 0.25 - idx * 0.03, 0.7)
        tone = _envelope_exp(tone, 0.15)
        tone = _fade(tone, 0.005, 0.03)
        parts.append(_concat(delay, tone))
    # Add a shimmer overtone
    shimmer = _sine(1567.98, 0.35, 0.15)  # G6
    shimmer = _envelope_exp(shimmer, 0.2)
    shimmer = _concat(_silence(0.15), shimmer)
    parts.append(shimmer)
    samples = _mix(*parts)
    return _normalize(samples, 0.7)


def _gen_error() -> list[float]:
    """Soft buzzer — two short low tones."""
    t1 = _sine(220.0, 0.08, 0.5)
    t1 = _envelope_exp(t1, 0.04)
    gap = _silence(0.04)
    t2 = _sine(180.0, 0.1, 0.5)
    t2 = _envelope_exp(t2, 0.05)
    samples = _concat(t1, gap, t2)
    samples = _fade(samples, 0.003, 0.01)
    return _normalize(samples, 0.45)


def _gen_timer_warning() -> list[float]:
    """Short tick/beep for timer warning."""
    tick = _sine(1000.0, 0.06, 0.5)
    tick = _envelope_exp(tick, 0.025)
    tick = _fade(tick, 0.002, 0.01)
    return _normalize(tick, 0.5)


def _gen_game_win() -> list[float]:
    """Victory fanfare — ascending arpeggio with harmonics."""
    # C major fanfare: C4-E4-G4-C5 with nice timing
    fanfare_notes = [
        (261.63, 0.15, 0.0),   # C4
        (329.63, 0.15, 0.12),  # E4
        (392.00, 0.15, 0.24),  # G4
        (523.25, 0.40, 0.36),  # C5 (held longer)
    ]
    parts: list[list[float]] = []
    for freq, dur, start in fanfare_notes:
        delay = _silence(start)
        # Fundamental + soft 2nd harmonic for richness
        tone = _mix(
            _sine(freq, dur, 0.6),
            _sine(freq * 2, dur, 0.15),
            _sine(freq * 3, dur, 0.05),
        )
        tone = _envelope_exp(tone, dur * 0.7)
        tone = _fade(tone, 0.005, 0.03)
        parts.append(_concat(delay, tone))

    # Final shimmering chord
    chord_start = 0.55
    chord_dur = 0.5
    chord_freqs = [523.25, 659.25, 783.99]  # C5, E5, G5
    for freq in chord_freqs:
        delay = _silence(chord_start)
        tone = _mix(
            _sine(freq, chord_dur, 0.35),
            _sine(freq * 2, chord_dur, 0.08),
        )
        tone = _envelope_exp(tone, 0.35)
        tone = _fade(tone, 0.01, 0.1)
        parts.append(_concat(delay, tone))

    samples = _mix(*parts)
    return _normalize(samples, 0.75)


def _gen_game_lose() -> list[float]:
    """Defeat sound — descending minor tones."""
    notes = [
        (392.00, 0.2, 0.0),   # G4
        (349.23, 0.2, 0.18),  # F4
        (311.13, 0.2, 0.36),  # Eb4
        (261.63, 0.5, 0.54),  # C4 (held)
    ]
    parts: list[list[float]] = []
    for freq, dur, start in notes:
        delay = _silence(start)
        tone = _mix(
            _sine(freq, dur, 0.5),
            _sine(freq * 0.998, dur, 0.3),  # slight detune for sadness
        )
        tone = _envelope_exp(tone, dur * 0.6)
        tone = _fade(tone, 0.008, 0.05)
        parts.append(_concat(delay, tone))
    samples = _mix(*parts)
    return _normalize(samples, 0.65)


def _gen_button_click() -> list[float]:
    """Subtle UI click — very short high-freq tick."""
    tick = _sine(2500.0, 0.008, 0.35)
    tick = _envelope_exp(tick, 0.003)
    body = _noise(0.006, 0.25)
    body = _bandpass_simple(body, 4000.0, 2.0)
    body = _envelope_exp(body, 0.003)
    samples = _mix(tick, body)
    samples = _fade(samples, 0.001, 0.003)
    return _normalize(samples, 0.35)


def _gen_thunder() -> list[float]:
    """Thunder/lightning crash for splash screen."""
    # Initial crack — bright noise burst
    crack = _noise(0.08, 1.0)
    crack = _bandpass_simple(crack, 3000.0, 2.0)
    crack = _envelope_exp(crack, 0.02)

    # Main rumble — filtered low noise with slow decay
    rumble_dur = 1.2
    rumble = _noise(rumble_dur, 1.0)
    rumble = _lowpass_simple(rumble, 200.0)
    # Manual decay envelope — starts at full, decays over the duration
    n_rumble = len(rumble)
    for i in range(n_rumble):
        t = i / _SAMPLE_RATE
        # Multi-stage decay for natural feel
        env = math.exp(-t / 0.4) * 0.8 + math.exp(-t / 1.0) * 0.2
        # Add some "rolling" modulation
        env *= 1.0 + 0.3 * math.sin(2.0 * math.pi * 3.5 * t)
        rumble[i] *= env

    # Mid-frequency body
    mid_body = _noise(0.8, 0.6)
    mid_body = _bandpass_simple(mid_body, 500.0, 1.0)
    mid_body = _envelope_exp(mid_body, 0.3)

    # Secondary crack (echo)
    crack2 = _noise(0.05, 0.5)
    crack2 = _bandpass_simple(crack2, 2500.0, 1.5)
    crack2 = _envelope_exp(crack2, 0.015)
    crack2 = _concat(_silence(0.15), crack2)

    # Very low sub-bass rumble
    sub = _sine(40.0, 0.8, 0.4)
    sub = _envelope_exp(sub, 0.35)

    samples = _mix(crack, rumble, mid_body, crack2, sub)
    samples = _fade(samples, 0.001, 0.15)
    return _normalize(samples, 0.85)


# ---------------------------------------------------------------------------
# Sound generators registry
# ---------------------------------------------------------------------------
_GENERATORS: dict[str, callable] = {
    "piece_move": _gen_piece_move,
    "piece_capture": _gen_piece_capture,
    "piece_king": _gen_piece_king,
    "error": _gen_error,
    "timer_warning": _gen_timer_warning,
    "game_win": _gen_game_win,
    "game_lose": _gen_game_lose,
    "button_click": _gen_button_click,
    "thunder": _gen_thunder,
}


# ---------------------------------------------------------------------------
# SoundManager
# ---------------------------------------------------------------------------

class SoundManager:
    """Generates and plays short sound effects for the draughts UI.

    Sounds are synthesised as WAV files in a temporary directory and played
    via QMediaPlayer.  If PyQt6.QtMultimedia is not installed the manager
    silently does nothing (all play_* methods become no-ops).
    """

    def __init__(self) -> None:
        self._enabled: bool = True
        self._tmp_dir: str | None = None
        self._players: dict[str, QMediaPlayer] = {}
        self._audio_outputs: dict[str, QAudioOutput] = {}
        self._wav_paths: dict[str, str] = {}
        self._available: bool = _HAS_MULTIMEDIA

        if not self._available:
            return

        # Create temp directory and generate WAV files
        self._tmp_dir = tempfile.mkdtemp(prefix="draughts_sounds_")
        atexit.register(self._cleanup)

        for name, generator in _GENERATORS.items():
            path = os.path.join(self._tmp_dir, f"{name}.wav")
            try:
                samples = generator()
                _write_wav(path, samples)
                self._wav_paths[name] = path
            except Exception:
                # If generation fails for one sound, skip it
                pass

    # -- Properties ---------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    # -- Internal -----------------------------------------------------------

    def _play(self, name: str) -> None:
        """Play a named sound effect."""
        if not self._enabled or not self._available:
            return
        path = self._wav_paths.get(name)
        if path is None:
            return

        try:
            # Reuse or create player for this sound
            player = self._players.get(name)
            if player is None:
                player = QMediaPlayer()
                audio_output = QAudioOutput()
                audio_output.setVolume(1.0)
                player.setAudioOutput(audio_output)
                self._players[name] = player
                self._audio_outputs[name] = audio_output

            # If currently playing, stop first so we can restart
            if player.isPlaying():
                player.stop()

            url = QUrl.fromLocalFile(os.path.abspath(path))
            player.setSource(url)
            player.play()
        except Exception:
            # Never let a sound failure crash the app
            pass

    def _cleanup(self) -> None:
        """Remove temporary WAV files."""
        # Stop all players first
        for player in self._players.values():
            try:
                player.stop()
            except Exception:
                pass
        self._players.clear()
        self._audio_outputs.clear()

        if self._tmp_dir and os.path.isdir(self._tmp_dir):
            try:
                shutil.rmtree(self._tmp_dir)
            except Exception:
                pass
            self._tmp_dir = None

    def __del__(self) -> None:
        self._cleanup()

    # -- Public play methods ------------------------------------------------

    def play_move(self) -> None:
        """Play piece-move sound (soft click/tap)."""
        self._play("piece_move")

    def play_capture(self) -> None:
        """Play piece-capture sound (impact)."""
        self._play("piece_capture")

    def play_king(self) -> None:
        """Play king-promotion sound (ascending arpeggio)."""
        self._play("piece_king")

    def play_error(self) -> None:
        """Play error/invalid-move sound (soft buzzer)."""
        self._play("error")

    def play_timer_warning(self) -> None:
        """Play timer-warning tick."""
        self._play("timer_warning")

    def play_game_win(self) -> None:
        """Play victory fanfare."""
        self._play("game_win")

    def play_game_lose(self) -> None:
        """Play defeat sound."""
        self._play("game_lose")

    def play_button_click(self) -> None:
        """Play subtle UI button click."""
        self._play("button_click")

    def play_thunder(self) -> None:
        """Play thunder crash (for splash screen)."""
        self._play("thunder")
