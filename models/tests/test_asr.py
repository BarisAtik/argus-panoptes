import json

import numpy as np
import pytest

from asr_nl import alignment, noise
from asr_nl.backends import Transcript
from asr_nl.evaluate import evaluate_run, hallucination, score_rows, slice_rows, summarize
from asr_nl.fetch_common_voice import build_manifest
from asr_nl.manifest import (
    Clip,
    audit,
    from_common_voice_tsv,
    read_manifest,
    sample_clips,
    write_manifest,
)
from asr_nl.normalize import normalize_dutch, number_to_dutch
from asr_nl.run import prediction_path, read_predictions, transcribe_condition


@pytest.mark.parametrize("n,word", [
    (0, "nul"), (13, "dertien"), (21, "eenentwintig"), (22, "tweeëntwintig"),
    (23, "drieëntwintig"), (24, "vierentwintig"), (30, "dertig"), (88, "achtentachtig"),
    (100, "honderd"), (101, "honderdeen"), (250, "tweehonderdvijftig"), (1000, "duizend"),
    (2024, "tweeduizend vierentwintig"), (1_000_000, "een miljoen"),
])
def test_dutch_numbers(n, word):
    assert number_to_dutch(n) == word


@pytest.mark.parametrize("raw,expected", [
    ("Dat is 12 euro.", "dat is twaalf euro"),
    ("Hij heeft ’n fiets, m'n vriend!", "hij heeft een fiets mijn vriend"),
    ("'t Is koud", "het is koud"),
    ("noord-holland", "noord holland"),
    ("12.500 mensen", "twaalfduizend vijfhonderd mensen"),
    ("3,5 kilo", "drie komma vijf kilo"),
    ("Café’s zijn open", "café's zijn open"),
])
def test_normalize(raw, expected):
    assert normalize_dutch(raw) == expected


def test_normalize_flags_are_independent():
    assert normalize_dutch("één", diacritics=False) == "een"
    assert normalize_dutch("12", numbers=False) == "12"
    assert normalize_dutch("'t", elisions=False) == "'t"


def test_alignment_matches_jiwer_on_random_sentences():
    jiwer = pytest.importorskip("jiwer")
    rng = np.random.default_rng(0)
    vocab = list("abcdefg")
    for _ in range(200):
        ref = " ".join(rng.choice(vocab, rng.integers(1, 12)))
        hyp = " ".join(rng.choice(vocab, rng.integers(1, 12)))
        ours = alignment.score(ref, hyp)
        theirs = jiwer.process_words(ref, hyp)
        total = theirs.substitutions + theirs.deletions + theirs.insertions
        assert ours.errors == total
        assert ours.reference_words == theirs.hits + theirs.substitutions + theirs.deletions


def test_compound_split_and_join_are_detected():
    split = alignment.score("het voetbalveld is groot", "het voetbal veld is groot")
    assert split.compound_splits == 1 and split.errors == 2 and split.compound_cost == 2
    joined = alignment.score("dit huis is te koop", "dit huis is tekoop")
    assert joined.compound_joins == 1 and joined.errors == 2
    plain = alignment.score("de kat slaapt", "de hond slaapt")
    assert plain.compound_cost == 0


def test_empty_hypothesis_is_all_deletions():
    counts = alignment.score("een twee", "")
    assert counts.deletions == 2 and counts.errors == 2


def test_char_errors():
    assert alignment.char_errors("kat", "kar") == (1, 3)


@pytest.mark.parametrize("snr", [20, 5, 0])
def test_mix_at_snr_hits_target(snr):
    rng = np.random.default_rng(0)
    clean = np.sin(np.linspace(0, 400, 16000)) * 0.1
    n = noise.white_noise(16000, rng)
    noisy = noise.mix_at_snr(clean, n, snr)
    measured = 20 * np.log10(noise.rms(clean) / noise.rms(noisy - clean))
    assert measured == pytest.approx(snr, abs=0.01)


def test_pink_noise_has_more_low_than_high_energy():
    spectrum = np.abs(np.fft.rfft(noise.pink_noise(32000, np.random.default_rng(0)))) ** 2
    assert spectrum[:1000].mean() > 10 * spectrum[-1000:].mean()


def test_telephone_removes_high_frequencies():
    t = np.arange(16000) / 16000
    high = noise.telephone(np.sin(2 * np.pi * 6000 * t))
    speech_band = noise.telephone(np.sin(2 * np.pi * 1000 * t))
    assert noise.rms(high) < 0.05 * noise.rms(speech_band)


@pytest.mark.parametrize("condition", sorted(noise.CONDITIONS))
def test_conditions_are_deterministic_and_keep_length(condition):
    audio = np.sin(np.linspace(0, 300, 8000)) * 0.2
    pool = [audio[::-1], audio * 0.5]
    a = noise.apply_condition(condition, audio, 123, pool)
    b = noise.apply_condition(condition, audio, 123, pool)
    assert len(a) == len(audio) and np.array_equal(a, b) and np.abs(a).max() <= 1.0


def test_unknown_condition_rejected():
    with pytest.raises(ValueError):
        noise.apply_condition("underwater", np.zeros(10), 0)


def clips_fixture(n_speakers=4, per_speaker=3):
    accents = ["Vlaams", "Randstad", "", "Limburg"]
    return [
        Clip(id=f"s{s}c{c}", path=f"{s}-{c}.wav", text=f"dit is zin {c} van spreker {s}",
             speaker=f"s{s}", accent=accents[s % 4], gender="f" if s % 2 else "m", age="twenties")
        for s in range(n_speakers) for c in range(per_speaker)
    ]


def test_manifest_round_trip(tmp_path):
    clips = clips_fixture()
    write_manifest(clips, tmp_path / "m.jsonl")
    assert read_manifest(tmp_path / "m.jsonl") == clips


def test_common_voice_tsv_parsing(tmp_path):
    tsv = tmp_path / "test.tsv"
    tsv.write_text(
        "client_id\tpath\tsentence\tup_votes\tage\tgender\taccents\n"
        'abc\tx1.mp3\tEen "mooie" dag\t2\tthirties\tmale_masculine\tVlaams\n'
        "def\t\tleeg\t2\t\t\t\n",
        encoding="utf-8",
    )
    clips = from_common_voice_tsv(tsv, "clips")
    assert len(clips) == 1
    assert clips[0].text == 'Een "mooie" dag' and clips[0].accent == "Vlaams"
    assert clips[0].speaker != "abc" and len(clips[0].speaker) == 12
    assert clips[0].path == "clips/x1.mp3"


def test_build_manifest_finds_extracted_layout(tmp_path):
    root = tmp_path / "cv-corpus" / "nl"
    (root / "clips").mkdir(parents=True)
    (root / "test.tsv").write_text("client_id\tpath\tsentence\na\tb.mp3\thallo\n",
                                   encoding="utf-8")
    manifest = build_manifest(tmp_path, tmp_path, "test", 10, 5, 0)
    assert len(read_manifest(manifest)) == 1


def test_sampling_caps_speakers_and_is_reproducible():
    clips = clips_fixture(2, 50) + clips_fixture(30, 1)
    clips = list({c.id: c for c in clips}.values())
    sample = sample_clips(clips, 20, per_speaker_cap=3, seed=1)
    counts = {}
    for clip in sample:
        counts[clip.speaker] = counts.get(clip.speaker, 0) + 1
    assert max(counts.values()) <= 3 and len(sample) == 20
    assert sample == sample_clips(clips, 20, per_speaker_cap=3, seed=1)


def test_audit_warns_on_dominant_speaker_and_missing_metadata():
    clips = clips_fixture(1, 90) + [
        Clip(id=str(i), path="p", text="t", speaker=f"x{i}") for i in range(20)
    ]
    report = audit(clips)
    assert any("dominate" in w for w in report["warnings"])
    assert report["speakers"] == 21


class EchoBackend:
    """Deterministic stand-in: repeats the reference, wrecked by noise, to exercise the pipeline."""

    name = "echo/model"

    def __init__(self, clips, wreck=0):
        self.queue = {i: c.text for i, c in enumerate(clips)}
        self.calls = 0
        self.wreck = wreck

    def transcribe(self, batch):
        out = []
        for audio in batch:
            index = int(round(audio[0] * 1000))
            words = self.queue.get(index, "").split()
            out.append(Transcript(" ".join(words[self.wreck:]), -0.1 * self.wreck, 0.1))
            self.calls += 1
        return out


def fake_loader(clips):
    index = {c.path: i for i, c in enumerate(clips)}
    return lambda path: np.full(1600, index[path] / 1000, dtype=np.float32)


def test_pipeline_end_to_end_and_resume(tmp_path):
    clips = clips_fixture(12, 3)
    backend = EchoBackend(clips)
    loader = fake_loader(clips)
    path = transcribe_condition(backend, clips, "clean", tmp_path, loader=loader, batch_size=4)
    assert path == prediction_path(tmp_path, "echo/model", "clean")
    calls = backend.calls
    transcribe_condition(backend, clips, "clean", tmp_path, loader=loader)
    assert backend.calls == calls, "finished clips must not be transcribed again"

    worse = EchoBackend(clips, wreck=1)
    worse.name = "worse"
    other = transcribe_condition(worse, clips, "clean", tmp_path, loader=loader, batch_size=4)
    report = evaluate_run(clips, [path, other], tmp_path / "out", provenance="smoke",
                          min_speakers=2)

    wers = {row["model"]: row["wer"] for row in report["summary"]}
    assert wers["echo/model"] == 0
    assert wers["worse"] == pytest.approx(1 / 7)
    pair = report["pairwise"][0]
    assert pair["a"] == "echo/model" and pair["difference"] < 0 and pair["high"] < 0
    assert report["meta"]["provenance"] == "smoke"
    assert (tmp_path / "out" / "report.md").read_text().startswith("> **SMOKE")
    json.loads((tmp_path / "out" / "report.json").read_text())


def test_slices_refuse_small_groups():
    clips = clips_fixture(4, 2)
    preds = [{"id": c.id, "hypothesis": c.text} for c in clips]
    rows = score_rows({c.id: c for c in clips}, preds)
    table = slice_rows(rows, "accent", min_speakers=2)
    assert all(r["wer"] is None and r["note"] == "too few speakers" for r in table)
    assert summarize(rows)["speakers"] == 4


def test_hallucination_counts_any_output():
    result = hallucination([{"hypothesis": ""}, {"hypothesis": "Bedankt voor het kijken"},
                            {"hypothesis": "..."}, {"hypothesis": "Bedankt voor het kijken"}])
    assert result["clips_with_output"] == 2 and result["mean_words"] == 2
    assert result["most_common"][0] == ("bedankt voor het kijken", 2)


def test_read_predictions_skips_blank_lines(tmp_path):
    path = tmp_path / "p.jsonl"
    path.write_text('{"id": "a"}\n\n', encoding="utf-8")
    assert read_predictions(path) == [{"id": "a"}]


@pytest.mark.torch
def test_real_whisper_architecture_on_tiny_random_weights(tmp_path):
    """Runs actual generate/decoding/log-prob code. Random weights, no download."""
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    from asr_nl.backends import TransformersWhisper

    torch.manual_seed(0)
    vocab = {f"tok{i}": i for i in range(50)}
    vocab.update({"<|nl|>": 44, "<|transcribe|>": 45, "<|notimestamps|>": 46})
    vocab_file = tmp_path / "vocab.json"
    vocab_file.write_text(json.dumps(vocab))
    merges = tmp_path / "merges.txt"
    merges.write_text("#version: 0.2\n")
    tokenizer = transformers.WhisperTokenizer(str(vocab_file), str(merges))
    config = transformers.WhisperConfig(
        vocab_size=50, d_model=16, encoder_layers=1, decoder_layers=1,
        encoder_attention_heads=2, decoder_attention_heads=2, encoder_ffn_dim=16,
        decoder_ffn_dim=16, max_source_positions=1500, max_target_positions=32,
        num_mel_bins=80, decoder_start_token_id=1, pad_token_id=0, eos_token_id=2,
        bos_token_id=1, suppress_tokens=[], begin_suppress_tokens=[],
    )
    model = transformers.WhisperForConditionalGeneration(config)
    model.generation_config = transformers.GenerationConfig(
        decoder_start_token_id=1, eos_token_id=2, pad_token_id=0, max_length=32,
    )
    # The multilingual path is the one real checkpoints take: language=nl, task=transcribe.
    model.generation_config.is_multilingual = True
    model.generation_config.lang_to_id = {"<|nl|>": 44}
    model.generation_config.task_to_id = {"transcribe": 45}
    model.generation_config.no_timestamps_token_id = 46
    processor = transformers.WhisperProcessor(transformers.WhisperFeatureExtractor(), tokenizer)
    backend = TransformersWhisper("tiny-random", device="cpu", model=model, processor=processor,
                                  max_new_tokens=5)
    result = backend.transcribe([np.zeros(8000, np.float32), np.ones(16000, np.float32) * 0.1])
    assert len(result) == 2 and all(isinstance(r.text, str) for r in result)
    assert all(r.avg_logprob is not None and r.avg_logprob <= 0 for r in result)
    assert backend._generate_kwargs()["language"] == "nl"


def test_load_audio_resamples_and_downmixes(tmp_path):
    soundfile = pytest.importorskip("soundfile")
    from asr_nl.run import load_audio

    path = tmp_path / "a.wav"
    stereo = np.tile(np.sin(np.linspace(0, 100, 8000))[:, None], (1, 2))
    soundfile.write(path, stereo, 8000)
    audio = load_audio(str(path))
    assert audio.ndim == 1 and len(audio) == 16000


def test_load_audio_reads_mp3_like_common_voice(tmp_path):
    import shutil
    import subprocess

    soundfile = pytest.importorskip("soundfile")
    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg to create an mp3")
    from asr_nl.run import load_audio

    wav, mp3 = tmp_path / "a.wav", tmp_path / "a.mp3"
    soundfile.write(wav, np.sin(np.linspace(0, 2000, 48000)) * 0.3, 48000)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(wav), str(mp3)], check=True)
    assert len(load_audio(str(mp3))) == pytest.approx(16000, abs=2000)


def test_cli_run_evaluate_and_audit(tmp_path, monkeypatch, capsys):
    import sys

    soundfile = pytest.importorskip("soundfile")
    yaml = pytest.importorskip("yaml")
    from asr_nl import cli

    clips = []
    for s in range(6):
        for c in range(2):
            path = tmp_path / f"{s}_{c}.wav"
            soundfile.write(path, np.sin(np.linspace(0, 200, 16000)) * 0.2, 16000)
            clips.append(Clip(f"{s}_{c}", str(path), "een twee drie", f"s{s}"))
    write_manifest(clips, tmp_path / "m.jsonl")

    class Fixed:
        name = "fixed"

        def transcribe(self, batch):
            return [Transcript("een twee", -0.5, 0.01) for _ in batch]

    monkeypatch.setattr(cli, "load_backend", lambda spec, language: Fixed())
    config = tmp_path / "c.yaml"
    config.write_text(yaml.safe_dump({
        "manifest": str(tmp_path / "m.jsonl"), "out_dir": str(tmp_path / "out"),
        "models": ["fixed"], "conditions": ["clean", "noise_only"], "min_speakers": 2,
    }))
    for command in (["run", "--config", str(config)], ["evaluate", "--config", str(config)]):
        monkeypatch.setattr(sys, "argv", ["cli", *command])
        cli.main()
        report = json.loads((tmp_path / "out" / "report.json").read_text())
        assert report["summary"][0]["wer"] == pytest.approx(1 / 3)
        assert report["hallucination"][0]["rate"] == 1
    monkeypatch.setattr(sys, "argv", ["cli", "audit", "--manifest", str(tmp_path / "m.jsonl")])
    cli.main()
    assert '"speakers": 6' in capsys.readouterr().out
