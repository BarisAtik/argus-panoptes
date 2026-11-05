"""Speech models behind one interface. Heavy imports stay inside the classes."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np


@dataclass
class Transcript:
    text: str
    avg_logprob: float | None = None
    seconds: float | None = None


class Backend(Protocol):
    name: str

    def transcribe(self, batch: Sequence[np.ndarray]) -> list[Transcript]: ...


def _pick_device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


class TransformersWhisper:
    """Hugging Face Whisper. Also records the mean token log-probability for later analysis."""

    def __init__(self, model_id: str, language: str = "nl", device: str | None = None,
                 model=None, processor=None, max_new_tokens: int = 200):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        self.name = model_id
        self.device = device or _pick_device()
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.processor = processor or AutoProcessor.from_pretrained(model_id)
        self.model = model or AutoModelForSpeechSeq2Seq.from_pretrained(model_id, dtype=dtype)
        self.model.to(self.device).eval()
        self.dtype = next(self.model.parameters()).dtype
        self.language = language
        self.max_new_tokens = max_new_tokens

    def _generate_kwargs(self) -> dict:
        kwargs: dict = {
            "max_new_tokens": self.max_new_tokens,
            "return_dict_in_generate": True,
            "output_scores": True,
        }
        if self.language and getattr(self.model.generation_config, "lang_to_id", None):
            kwargs.update(language=self.language, task="transcribe")
        return kwargs

    def transcribe(self, batch: Sequence[np.ndarray]) -> list[Transcript]:
        import torch

        start = time.perf_counter()
        inputs = self.processor.feature_extractor(
            list(batch), sampling_rate=16_000, return_tensors="pt"
        )
        features = inputs.input_features.to(self.device, dtype=self.dtype)
        with torch.inference_mode():
            output = self.model.generate(features, **self._generate_kwargs())
            scores = self.model.compute_transition_scores(
                output.sequences, output.scores, normalize_logits=True
            )
        texts = self.processor.tokenizer.batch_decode(output.sequences, skip_special_tokens=True)
        finite = torch.isfinite(scores) & (scores != 0)
        lengths = finite.sum(dim=1).clamp(min=1)
        logprobs = (scores.nan_to_num(0, neginf=0) * finite).sum(dim=1) / lengths
        per_clip = (time.perf_counter() - start) / max(1, len(batch))
        return [
            Transcript(text.strip(), float(lp), per_clip)
            for text, lp in zip(texts, logprobs.cpu().tolist())
        ]


class FasterWhisper:
    """CTranslate2 Whisper (`pip install .[asr-fast]`). Much faster on CPU or a laptop GPU."""

    def __init__(self, model_id: str, language: str = "nl", device: str = "auto",
                 compute_type: str = "auto"):
        from faster_whisper import WhisperModel

        self.name = f"faster:{model_id}"
        self.language = language
        self.model = WhisperModel(model_id, device=device, compute_type=compute_type)

    def transcribe(self, batch: Sequence[np.ndarray]) -> list[Transcript]:
        results = []
        for audio in batch:
            start = time.perf_counter()
            segments, _ = self.model.transcribe(
                audio.astype(np.float32), language=self.language, beam_size=5,
                condition_on_previous_text=False,
            )
            segments = list(segments)
            weights = [max(1, len(s.tokens)) for s in segments]
            logprob = (
                float(np.average([s.avg_logprob for s in segments], weights=weights))
                if segments else None
            )
            results.append(Transcript(" ".join(s.text.strip() for s in segments), logprob,
                                      time.perf_counter() - start))
        return results


def _find_model_file(folder: Path, pattern: str) -> str:
    """Prefer the int8 export: it is what makes these models bearable on a CPU."""
    matches = sorted(folder.glob(pattern), key=lambda path: ("int8" not in path.name, path.name))
    if not matches:
        raise FileNotFoundError(f"no {pattern} in {folder}")
    return str(matches[0])


class SherpaOffline:
    """ONNX models through sherpa-onnx (`pip install .[asr-onnx]`): no torch, CPU friendly.

    `kind` is "whisper", or "transducer" for NeMo Parakeet TDT 0.6b v3, a non-Whisper comparison
    that lists Dutch among its languages. Parakeet detects the language itself, so `language`
    only applies to Whisper. sherpa-onnx gives no log-probability, so `avg_logprob` stays None
    and the confidence analysis skips these models.
    """

    def __init__(self, kind: str, folder: str, language: str = "nl", num_threads: int = 2):
        import sherpa_onnx

        root = Path(folder)
        self.name = f"sherpa-{kind}:{root.name}"
        recognizer = sherpa_onnx.OfflineRecognizer
        if kind == "whisper":
            self.recognizer = recognizer.from_whisper(
                encoder=_find_model_file(root, "*encoder*.onnx"),
                decoder=_find_model_file(root, "*decoder*.onnx"),
                tokens=_find_model_file(root, "*tokens.txt"),
                language=language, task="transcribe", num_threads=num_threads,
            )
        elif kind == "transducer":
            self.recognizer = recognizer.from_transducer(
                encoder=_find_model_file(root, "*encoder*.onnx"),
                decoder=_find_model_file(root, "*decoder*.onnx"),
                joiner=_find_model_file(root, "*joiner*.onnx"),
                tokens=_find_model_file(root, "*tokens.txt"),
                num_threads=num_threads, model_type="nemo_transducer",
            )
        else:
            raise ValueError(f"unknown sherpa model kind {kind!r}")

    def transcribe(self, batch: Sequence[np.ndarray]) -> list[Transcript]:
        results = []
        for audio in batch:
            start = time.perf_counter()
            stream = self.recognizer.create_stream()
            stream.accept_waveform(16_000, audio.astype(np.float32))
            self.recognizer.decode_stream(stream)
            results.append(Transcript(stream.result.text.strip(), None,
                                      time.perf_counter() - start))
        return results


def load_backend(spec: str, language: str = "nl") -> Backend:
    """`openai/whisper-small` (Transformers), `faster:large-v3` (faster-whisper),
    `sherpa-whisper:<folder>` or `sherpa-transducer:<folder>` (ONNX)."""
    if spec.startswith(("sherpa-whisper:", "sherpa-transducer:")):
        kind, _, folder = spec.removeprefix("sherpa-").partition(":")
        return SherpaOffline(kind, folder, language=language)
    if spec.startswith("faster:"):
        return FasterWhisper(spec.removeprefix("faster:"), language=language)
    return TransformersWhisper(spec, language=language)
