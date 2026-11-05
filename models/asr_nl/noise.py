"""Controlled degradations. Same clip, same seed, every model: differences are the models'."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy import signal

SAMPLE_RATE = 16_000


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio)) + 1e-12))


def white_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.standard_normal(n)


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f noise: spectrally closer to fans and traffic than white noise."""
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n)
    freqs[0] = freqs[1] if n > 1 else 1.0
    return np.fft.irfft(spectrum / np.sqrt(freqs), n)


def babble(n: int, rng: np.random.Generator, pool: Sequence[np.ndarray], voices: int = 6):
    """Overlap several other clips: the hardest common noise, because it is speech."""
    if not len(pool):
        raise ValueError("babble needs a pool of other clips")
    mix = np.zeros(n)
    for _ in range(voices):
        clip = pool[rng.integers(len(pool))]
        repeated = np.resize(clip, n)
        mix += np.roll(repeated, rng.integers(n)) / (rms(repeated) + 1e-9)
    return mix


def mix_at_snr(clean: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    gain = rms(clean) / (rms(noise) * 10 ** (snr_db / 20))
    mixed = clean + gain * noise
    peak = np.abs(mixed).max()
    return mixed / peak * 0.99 if peak > 0.99 else mixed


def telephone(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Narrowband phone line: 300-3400 Hz at 8 kHz, then back to the model's sample rate."""
    sos = signal.butter(6, [300, 3400], btype="band", fs=sample_rate, output="sos")
    filtered = signal.sosfilt(sos, audio)
    low = signal.resample_poly(filtered, 8000, sample_rate)
    return signal.resample_poly(low, sample_rate, 8000)[: len(audio)]


def reverb(audio: np.ndarray, rng: np.random.Generator, rt60: float = 0.6) -> np.ndarray:
    """Exponentially decaying noise as a synthetic room impulse response."""
    n = int(rt60 * SAMPLE_RATE)
    envelope = np.exp(-6.91 * np.arange(n) / n)  # -60 dB at rt60
    impulse = rng.standard_normal(n) * envelope
    impulse[0] = 1.0
    wet = signal.fftconvolve(audio, impulse)[: len(audio)]
    return wet / (np.abs(wet).max() + 1e-9) * max(np.abs(audio).max(), 1e-3)


CONDITIONS = {"clean", "white_20", "pink_10", "pink_0", "babble_10", "babble_5", "telephone",
              "reverb", "noise_only"}


def apply_condition(
    condition: str,
    audio: np.ndarray,
    seed: int,
    pool: Sequence[np.ndarray] = (),
) -> np.ndarray:
    """Degrade one clip. `seed` should come from the clip id so runs are reproducible."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}; choose from {sorted(CONDITIONS)}")
    rng = np.random.default_rng(seed)
    n = len(audio)
    if condition == "clean":
        return audio
    if condition == "white_20":
        return mix_at_snr(audio, white_noise(n, rng), 20)
    if condition == "pink_10":
        return mix_at_snr(audio, pink_noise(n, rng), 10)
    if condition == "pink_0":
        return mix_at_snr(audio, pink_noise(n, rng), 0)
    if condition == "babble_10":
        return mix_at_snr(audio, babble(n, rng, pool), 10)
    if condition == "babble_5":
        return mix_at_snr(audio, babble(n, rng, pool), 5)
    if condition == "telephone":
        return telephone(audio)
    if condition == "reverb":
        return reverb(audio, rng)
    # noise_only: no speech at all. Anything the model outputs is hallucinated.
    noise = pink_noise(n, rng)
    return noise / rms(noise) * max(rms(audio), 1e-3)
