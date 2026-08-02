"""Unit tests for the P-3 bake-off probe's pure core. No engine, no audio.

Every ASR import in the probe is lazy (inside its adapter), so importing the module
and exercising the aligner / WER / proper-noun / ruling / arg-parse / --dry-run never
loads onnx-asr, moonshine-voice, faster-whisper, or even jiwer - the CLAUDE.md rule:
no test loads an ASR engine, no test calls the Claude API. The headline metrics use
the local aligner precisely so these tests need nothing installed.
"""
import measure_p3_stt as p3


# --------------------------------------------------------------------------- #
# normalize / normalize_terms
# --------------------------------------------------------------------------- #
def test_normalize_lowercases_and_strips_punctuation():
    assert p3.normalize("Hello, Malang!  How's it?") == ["hello", "malang", "how's", "it"]


def test_normalize_unifies_apostrophes_and_drops_bare_ones():
    assert p3.normalize("don’t  '  stop") == ["don't", "stop"]


def test_normalize_terms_flattens_multiword_names():
    assert p3.normalize_terms(["Wali Khan", "Malang"]) == {"wali", "khan", "malang"}


# --------------------------------------------------------------------------- #
# align - the shared spine. Substitution / deletion / insertion / equal.
# --------------------------------------------------------------------------- #
def test_align_all_equal():
    ops = p3.align(["a", "b", "c"], ["a", "b", "c"])
    assert [o[0] for o in ops] == ["equal", "equal", "equal"]


def test_align_substitution():
    ops = p3.align(["the", "cat"], ["the", "hat"])
    assert ops[1] == ("sub", "cat", "hat")


def test_align_deletion_and_insertion():
    # ref has an extra word -> deletion; hyp has an extra word -> insertion.
    del_ops = p3.align(["a", "b", "c"], ["a", "c"])
    assert ("del", "b", None) in del_ops
    ins_ops = p3.align(["a", "c"], ["a", "b", "c"])
    assert ("ins", None, "b") in ins_ops


def test_align_empty_hyp_is_all_deletions():
    ops = p3.align(["a", "b"], [])
    assert [o[0] for o in ops] == ["del", "del"]


# --------------------------------------------------------------------------- #
# WER math
# --------------------------------------------------------------------------- #
def test_wer_counts_and_rate_basic():
    # ref 4 words, one substitution -> WER 1/4.
    ops = p3.align(["one", "two", "three", "four"], ["one", "two", "THREE".lower(), "four"])
    counts = p3.wer_counts(ops)
    assert counts["N"] == 4
    ops2 = p3.align(["a", "b", "c", "d"], ["a", "x", "c", "d"])
    c2 = p3.wer_counts(ops2)
    assert (c2["S"], c2["D"], c2["I"], c2["N"]) == (1, 0, 0, 4)
    assert p3.wer_rate(c2) == 0.25


def test_wer_rate_counts_insertions_against_ref_length():
    # ref 2 words, hyp adds one word -> 1 insertion / 2 = 0.5.
    ops = p3.align(["a", "b"], ["a", "b", "c"])
    assert p3.wer_rate(p3.wer_counts(ops)) == 0.5


def test_wer_rate_empty_reference_is_none():
    assert p3.wer_rate({"S": 0, "D": 0, "I": 3, "N": 0}) is None


# --------------------------------------------------------------------------- #
# proper-noun-error-rate - errors only over tagged ref tokens.
# --------------------------------------------------------------------------- #
def test_proper_noun_counts_only_tagged_tokens():
    ref = ["call", "malang", "about", "zarak"]
    hyp = ["call", "malong", "about", "zarak"]   # malang mis-heard, zarak correct
    ops = p3.align(ref, hyp)
    pn = p3.proper_noun_counts(ops, {"malang", "zarak"})
    assert pn == {"errors": 1, "total": 2}
    assert p3.rate(pn, "errors", "total") == 0.5


def test_proper_noun_rate_none_when_no_proper_nouns():
    ops = p3.align(["a", "b"], ["a", "b"])
    assert p3.rate(p3.proper_noun_counts(ops, set()), "errors", "total") is None


# --------------------------------------------------------------------------- #
# seed vocab - the FR-18 near-miss pairs.
# --------------------------------------------------------------------------- #
def test_seed_from_alignment_captures_substitution_and_deletion():
    ops = p3.align(["malang", "and", "zarak"], ["malong", "and"])
    seed = p3.seed_from_alignment(ops, {"malang", "zarak"})
    names = {(s["name"], s["op"], s["heard"]) for s in seed}
    assert ("malang", "sub", "malong") in names
    assert ("zarak", "del", None) in names


# --------------------------------------------------------------------------- #
# percentiles - self-contained, nearest-rank (parity with P-2).
# --------------------------------------------------------------------------- #
def test_percentiles_empty_and_basic():
    assert p3.percentiles([], (50, 95)) == {50: None, 95: None}
    assert p3.percentiles(list(range(1, 11)), (50, 95)) == {50: 5, 95: 10}


# --------------------------------------------------------------------------- #
# memory-path ruling - the three pre-decided branches (spec section 9).
# --------------------------------------------------------------------------- #
def test_memory_path_ruling_parakeet_solo_when_within_noise():
    # Parakeet's code-switched proper-noun rate within noise_floor of whisper's.
    key, _ = p3.memory_path_ruling(p_cs=0.10, w_cs=0.09, p_overall=0.08, w_overall=0.075,
                                   noise_floor=0.02)
    assert key == "parakeet-solo"


def test_memory_path_ruling_whisper_swap_when_dominates_overall():
    key, _ = p3.memory_path_ruling(p_cs=0.30, w_cs=0.10, p_overall=0.20, w_overall=0.10,
                                   noise_floor=0.02)
    assert key == "whisper-swap"


def test_memory_path_ruling_hybrid_when_gap_only_on_codeswitch():
    # Big code-switched proper-noun gap, but overall WER within noise -> hybrid.
    key, _ = p3.memory_path_ruling(p_cs=0.30, w_cs=0.10, p_overall=0.08, w_overall=0.075,
                                   noise_floor=0.02)
    assert key == "hybrid"


def test_memory_path_ruling_undetermined_on_missing():
    key, _ = p3.memory_path_ruling(None, 0.1, 0.1, 0.1)
    assert key == "undetermined"


# --------------------------------------------------------------------------- #
# moonshine live-WER health - the ~12% boundary (spec section 9).
# --------------------------------------------------------------------------- #
def test_moonshine_health_boundary():
    assert p3.moonshine_health(0.11)[0] == "ok"
    assert p3.moonshine_health(0.12)[0] == "ok"          # <= tolerance is ok
    assert p3.moonshine_health(0.13)[0] == "recalibrate"
    assert p3.moonshine_health(None)[0] == "unknown"


# --------------------------------------------------------------------------- #
# arg parsing + model resolution
# --------------------------------------------------------------------------- #
def test_parse_args_defaults():
    args = p3.parse_args([])
    assert args.corpus == "corpus/p3"
    assert args.models == ["all"]
    assert args.threads == 3
    assert args.noise_floor == p3.NOISE_FLOOR
    assert args.dry_run is False
    assert args.smoke is False


def test_resolve_models_expands_all_in_canonical_order():
    assert p3.resolve_models(["all"]) == list(p3.ALL_MODELS)
    assert p3.resolve_models(["whisper-turbo", "parakeet"]) == ["parakeet", "whisper-turbo"]


# --------------------------------------------------------------------------- #
# score_model - micro-averaging across a tiny synthetic corpus (no audio).
# --------------------------------------------------------------------------- #
def test_score_model_aggregates_and_flags_empty():
    entries = [
        {"id": "monologue", "register": "monologue",
         "ref_tokens": ["hello", "there", "friend"], "pn": set()},
        {"id": "codeswitch", "register": "codeswitch",
         "ref_tokens": ["call", "malang", "now"], "pn": {"malang"}},
    ]
    hyps = {"monologue": "hello there friend", "codeswitch": ""}  # second empty
    r = p3.score_model(entries, hyps)
    assert r["empty"] == 1                                   # the empty codeswitch hyp
    assert r["by_register"]["monologue"]["wer"]["rate"] == 0.0
    # codeswitch: whole 3-word ref deleted -> WER 1.0, proper-noun rate 1.0
    assert r["by_register"]["codeswitch"]["wer"]["rate"] == 1.0
    assert r["by_register"]["codeswitch"]["pn"]["rate"] == 1.0


# --------------------------------------------------------------------------- #
# --dry-run - offline smoke: exit 0, both rulings printed, no engine loaded.
# --------------------------------------------------------------------------- #
def test_dry_run_exits_zero_without_engine(capsys):
    rc = p3.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "GATE: P-3" in out
    assert "MEMORY-PATH RULING" in out
    assert "LIVE-PATH RULING" in out
    assert "no engine was loaded" in out.lower()
