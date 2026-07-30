"""Unit tests for the P-2 probe's pure core. No engine, no audio, nothing installed.

The probe's `kokoro_onnx` import is lazy (inside the engine layer), so importing
the module and exercising percentiles / RTF math / gate branches / corpus / arg
parsing / --dry-run never loads onnxruntime or the model - which is the CLAUDE.md
rule: no test loads the TTS engine, no test calls the Claude API.
"""
import measure_p2_kokoro as p2


# --------------------------------------------------------------------------- #
# percentiles - nearest-rank, self-contained (not imported from P-1).
# --------------------------------------------------------------------------- #
def test_percentiles_empty_maps_to_none():
    assert p2.percentiles([], (50, 95)) == {50: None, 95: None}


def test_percentiles_single_value():
    assert p2.percentiles([0.5], (50, 95)) == {50: 0.5, 95: 0.5}


def test_percentiles_nearest_rank_on_1_to_10():
    out = p2.percentiles(list(range(1, 11)), (50, 95))
    assert out == {50: 5, 95: 10}


def test_percentiles_is_order_independent():
    a = p2.percentiles([9, 1, 5, 7, 3], (50,))
    b = p2.percentiles([1, 3, 5, 7, 9], (50,))
    assert a == b == {50: 5}


# --------------------------------------------------------------------------- #
# length_band - the HP16 length spread.
# --------------------------------------------------------------------------- #
def test_length_band_boundaries():
    assert p2.length_band("one two three four five") == "short"        # 5 words
    assert p2.length_band("one two three four five six") == "medium"   # 6 words
    assert p2.length_band(" ".join(["w"] * 25)) == "medium"           # 25 words
    assert p2.length_band(" ".join(["w"] * 26)) == "long"             # 26 words


# --------------------------------------------------------------------------- #
# compute_rtf - the whole point; None on zero-length audio (silence).
# --------------------------------------------------------------------------- #
def test_compute_rtf_basic():
    # 24000 samples @ 24kHz = 1.0s of audio; 0.5s wall -> RTF 0.5.
    assert p2.compute_rtf(0.5, 24000, 24000) == 0.5


def test_compute_rtf_faster_and_slower_than_realtime():
    assert p2.compute_rtf(0.4, 48000, 24000) == 0.2   # 2s audio in 0.4s wall
    assert p2.compute_rtf(2.0, 24000, 24000) == 2.0   # 1s audio took 2s -> slower than real time


def test_compute_rtf_zero_samples_is_none():
    # The silent-synthesis case: no audio -> no number, never a misleading zero.
    assert p2.compute_rtf(0.5, 0, 24000) is None
    assert p2.compute_rtf(0.5, 24000, 0) is None


def test_compute_rtf_reads_sample_rate_not_hardcoded():
    # Same samples, different declared rate -> different duration -> different RTF.
    assert p2.compute_rtf(1.0, 24000, 24000) == 1.0
    assert p2.compute_rtf(1.0, 24000, 48000) == 2.0


# --------------------------------------------------------------------------- #
# is_silent - rule 2 guard.
# --------------------------------------------------------------------------- #
def test_is_silent():
    assert p2.is_silent(0.0) is True
    assert p2.is_silent(None) is True
    assert p2.is_silent(0.005) is True          # below default floor 0.01
    assert p2.is_silent(0.5) is False


# --------------------------------------------------------------------------- #
# corpus - fixed, 10 sentences, spans the length range, includes the name line.
# --------------------------------------------------------------------------- #
def test_corpus_has_ten_sentences():
    assert len(p2.CORPUS) == 10


def test_corpus_spans_all_length_bands():
    bands = {p2.length_band(s) for s in p2.CORPUS}
    assert bands == {"short", "medium", "long"}


def test_corpus_includes_the_name_line():
    assert any("Malang" in s for s in p2.CORPUS)


# --------------------------------------------------------------------------- #
# gate ruling - the pre-decided branches (spec section 9).
# --------------------------------------------------------------------------- #
def test_gate_ruling_branches():
    assert "CONFIRMED" in p2._gate_ruling(0.5)
    assert "FAILS" in p2._gate_ruling(0.8)          # boundary: >= 0.8 fails
    assert "FAILS" in p2._gate_ruling(0.95)
    assert "no RTF" in p2._gate_ruling(None)


# --------------------------------------------------------------------------- #
# drift note - thermal early-warning flag.
# --------------------------------------------------------------------------- #
def test_drift_note_flags_thermal_throttle():
    assert "THERMAL DRIFT" in p2._drift_note(0.50, 0.60)   # +20% > 15%
    assert "THERMAL DRIFT" not in p2._drift_note(0.50, 0.55)  # +10%
    assert p2._drift_note(None, 0.5) == "n/a"


# --------------------------------------------------------------------------- #
# parse_args - defaults and overrides.
# --------------------------------------------------------------------------- #
def test_parse_args_defaults():
    args = p2.parse_args([])
    assert args.rounds == 5
    assert args.voice == "af_heart"
    assert args.threads == 3
    assert args.build == "standard"
    assert args.trim is True
    assert args.label == ""
    assert args.dry_run is False


def test_parse_args_overrides():
    args = p2.parse_args(
        ["--rounds", "3", "--voice", "am_adam", "--threads", "2",
         "--build", "quantized", "--no-trim", "--label", "battery", "--dry-run"]
    )
    assert args.rounds == 3
    assert args.voice == "am_adam"
    assert args.threads == 2
    assert args.build == "quantized"
    assert args.trim is False
    assert args.label == "battery"
    assert args.dry_run is True


def test_model_path_follows_build():
    std = p2.parse_args(["--build", "standard"])
    quant = p2.parse_args(["--build", "quantized"])
    assert p2._model_path(std).endswith("kokoro-v1.0.onnx")
    assert p2._model_path(quant).endswith("kokoro-v1.0.int8.onnx")
    override = p2.parse_args(["--model-path", "custom/x.onnx"])
    assert p2._model_path(override) == "custom/x.onnx"


# --------------------------------------------------------------------------- #
# run_corpus - the silence guard must cover EVERY synthesis, not just the warm-up
# (latency-auditor BLOCKING finding). Driven by a fake synth: no engine, no numpy.
# --------------------------------------------------------------------------- #
def _ok_synth(_text):
    # 1.0s of audio synthesized in 0.5s wall, healthy peak -> RTF 0.5.
    return (0.5, 24000, 24000, 0.5)


def test_run_corpus_happy_path_collects_every_item():
    sbb, rbr, elapsed, error = p2.run_corpus(_ok_synth, rounds=2, silence_floor=0.01)
    assert error is None
    assert sum(len(v) for v in sbb.values()) == 2 * len(p2.CORPUS)
    assert set(rbr) == {1, 2}
    assert elapsed >= 0.0


def test_run_corpus_aborts_on_midrun_full_length_silence():
    # The exact BLOCKING case: a FULL-LENGTH but silent clip (real duration, zero
    # peak) mid-run. It would compute a normal-looking RTF and pass if not caught.
    state = {"i": 0}

    def synth(_text):
        state["i"] += 1
        peak = 0.0 if state["i"] == 7 else 0.5   # item 7 comes back silent
        return (0.5, 24000, 24000, peak)

    sbb, rbr, elapsed, error = p2.run_corpus(synth, rounds=5, silence_floor=0.01)
    assert error is not None and "SILENT" in error
    assert sum(len(v) for v in sbb.values()) == 6   # aborted at item 7, nothing after


def test_run_corpus_aborts_on_zero_length():
    def synth(_text):
        return (0.5, 0, 24000, 0.0)   # no samples at all

    sbb, rbr, elapsed, error = p2.run_corpus(synth, rounds=1, silence_floor=0.01)
    assert error is not None
    assert sum(len(v) for v in sbb.values()) == 0


def test_run_corpus_aborts_on_zero_sample_rate():
    def synth(_text):
        return (0.5, 24000, 0, 0.5)   # samples present but sr=0 -> compute_rtf None

    sbb, rbr, elapsed, error = p2.run_corpus(synth, rounds=1, silence_floor=0.01)
    assert error is not None and "ZERO-DURATION" in error


# --------------------------------------------------------------------------- #
# --dry-run - offline smoke: exit 0, ruling block, no engine loaded.
# --------------------------------------------------------------------------- #
def test_dry_run_exits_zero_without_engine(capsys):
    rc = p2.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "GATE: P-2" in out
    assert "CONFIRMED" in out          # synthetic numbers are < 0.8
    assert "by length:" in out         # the per-band breakdown is present
    assert "no engine was loaded" in out.lower()
