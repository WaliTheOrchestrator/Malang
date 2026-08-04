"""Unit tests for the P-4a ear-probe pure core. No engine, no audio, no numpy.

The probe's kokoro_onnx / sounddevice imports are lazy (inside the engine layer),
so importing the module and exercising ABX stats / gate branches / trial building /
name parsing / template render / --dry-run never loads onnxruntime or PortAudio -
the CLAUDE.md rule: no test loads the TTS engine, no test opens a device.
"""
import measure_p4_int8_ear as ear


# --------------------------------------------------------------------------- #
# binom_sf_ge - the ABX p-value (P(X>=k) under p=0.5).
# --------------------------------------------------------------------------- #
def test_binom_sf_ge_symmetry_and_bounds():
    assert ear.binom_sf_ge(0, 10) == 1.0            # >=0 always
    assert abs(ear.binom_sf_ge(5, 10) - 0.623046875) < 1e-9   # median-ish
    assert abs(ear.binom_sf_ge(10, 10) - (0.5 ** 10)) < 1e-12  # all correct
    assert ear.binom_sf_ge(3, 0) == 1.0             # no trials -> no evidence


def test_binom_sf_ge_all_correct_24_is_tiny():
    assert ear.binom_sf_ge(24, 24) < 1e-6           # 24/24 is overwhelming


# --------------------------------------------------------------------------- #
# abx_ruling - distinguishable iff p<=alpha.
# --------------------------------------------------------------------------- #
def test_abx_ruling_chance_is_indistinguishable():
    r = ear.abx_ruling(12, 24)                      # exactly chance
    assert r["distinguishable"] is False
    assert r["p_value"] > 0.05


def test_abx_ruling_strong_signal_is_distinguishable():
    r = ear.abx_ruling(20, 24)                      # well above chance
    assert r["distinguishable"] is True
    assert r["p_value"] <= 0.05


def test_abx_ruling_boundary_around_alpha():
    # 17/24 correct -> p ~0.032 <= 0.05 -> distinguishable.
    r = ear.abx_ruling(17, 24)
    assert r["distinguishable"] is True
    # 16/24 -> p ~0.076 > 0.05 -> not.
    assert ear.abx_ruling(16, 24)["distinguishable"] is False


# --------------------------------------------------------------------------- #
# p4a_gate - the three pre-decided branches (spec §9/§12).
# --------------------------------------------------------------------------- #
def test_gate_negative_control_failed_takes_priority():
    # Even if selective looks indistinguishable, a control that was NOT caught
    # invalidates the whole instrument.
    selective = ear.abx_ruling(12, 24)             # indistinguishable
    control = ear.abx_ruling(13, 24)               # control NOT caught
    verdict, _ = ear.p4a_gate(selective, control)
    assert "NEGATIVE CONTROL FAILED" in verdict


def test_gate_int8_distinguishable_ships_fp32():
    selective = ear.abx_ruling(21, 24)             # caught -> distinguishable
    control = ear.abx_ruling(22, 24)               # control caught
    verdict, _ = ear.p4a_gate(selective, control)
    assert "SHIP fp32" in verdict


def test_gate_int8_indistinguishable_ships_int8():
    selective = ear.abx_ruling(12, 24)             # not caught
    control = ear.abx_ruling(21, 24)               # control caught -> instrument sound
    verdict, _ = ear.p4a_gate(selective, control)
    assert "SHIP selective-int8" in verdict


def test_gate_without_control_still_rules_on_selective():
    verdict, _ = ear.p4a_gate(ear.abx_ruling(12, 24), None)
    assert "SHIP selective-int8" in verdict


# --------------------------------------------------------------------------- #
# build_trials - deterministic from seed; well-formed ABX trials.
# --------------------------------------------------------------------------- #
def test_build_trials_is_deterministic_for_a_seed():
    a = ear.build_trials(("fp32", "selective"), 24, seed=7, n_sentences=10)
    b = ear.build_trials(("fp32", "selective"), 24, seed=7, n_sentences=10)
    assert a == b


def test_build_trials_different_seed_differs():
    a = ear.build_trials(("fp32", "selective"), 24, seed=1, n_sentences=10)
    b = ear.build_trials(("fp32", "selective"), 24, seed=2, n_sentences=10)
    assert a != b


def test_build_trials_are_well_formed():
    trials = ear.build_trials(("fp32", "selective"), 24, seed=5, n_sentences=10)
    assert len(trials) == 24
    for t in trials:
        assert {t.a_build, t.b_build} == {"fp32", "selective"}   # A/B are the two builds
        assert t.x_build in ("fp32", "selective")                # X is one of them
        assert 0 <= t.sentence_idx < 10


# --------------------------------------------------------------------------- #
# correct_slot / grade / tally_correct.
# --------------------------------------------------------------------------- #
def test_correct_slot_and_grade():
    t = ear.Trial(sentence_idx=0, x_build="fp32", a_build="fp32", b_build="selective")
    assert ear.correct_slot(t) == "a"
    assert ear.grade(t, "a") is True
    assert ear.grade(t, "B") is False
    t2 = ear.Trial(0, "selective", "fp32", "selective")
    assert ear.correct_slot(t2) == "b"


def test_tally_correct_counts_only_matches():
    trials = [ear.Trial(0, "fp32", "fp32", "selective"),
              ear.Trial(1, "selective", "fp32", "selective")]
    assert ear.tally_correct(trials, ["a", "b"]) == 2   # both right
    assert ear.tally_correct(trials, ["b", "b"]) == 1   # first wrong


# --------------------------------------------------------------------------- #
# parse_names - the git-ignored file format; never in a tracked file.
# --------------------------------------------------------------------------- #
def test_parse_names_tsv_with_and_without_ipa():
    text = "# comment\n\nNAME1\tZarak\tzˈɑːɾək\nNAME2\tKarim\n"
    names = ear.parse_names(text)
    assert names["NAME1"] == ("Zarak", "zˈɑːɾək")
    assert names["NAME2"] == ("Karim", None)
    assert "comment" not in names


def test_parse_names_ignores_malformed_lines():
    names = ear.parse_names("ONLYONECOLUMN\n\t\nGOOD\tName\n")
    assert list(names) == ["GOOD"]


# --------------------------------------------------------------------------- #
# render_template - placeholder injection; unknown placeholders stay visible.
# --------------------------------------------------------------------------- #
def test_render_template_injects_names():
    tmpl = "# header\nMalang called {NAME1}.\n{NAME1} met {NAME2}.\n"
    names = {"NAME1": ("Zarak", None), "NAME2": ("Karim", None)}
    out = ear.render_template(tmpl, names)
    assert out == ["Malang called Zarak.", "Zarak met Karim."]


def test_render_template_leaves_unknown_placeholder_visible():
    out = ear.render_template("Hi {MISSING}.", {})
    assert out == ["Hi {MISSING}."]                 # never silently blanked


# --------------------------------------------------------------------------- #
# --dry-run - offline smoke: exit 0, ruling block, no engine loaded.
# --------------------------------------------------------------------------- #
def test_dry_run_exits_zero_without_engine(capsys):
    rc = ear.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "GATE: P-4a" in out
    assert "SHIP selective-int8" in out             # synthetic: control caught, selective not
    assert "negative control" in out.lower()
    assert "no engine loaded" in out.lower()


def test_parse_args_defaults_and_overrides():
    d = ear.parse_args([])
    assert d.builds == "fp32,selective,blind"
    assert d.trials == 24 and d.voice == "af_heart" and d.dry_run is False
    o = ear.parse_args(["--trials", "40", "--seed", "9", "--grader", "w", "--dry-run"])
    assert o.trials == 40 and o.seed == 9 and o.grader == "w" and o.dry_run is True
