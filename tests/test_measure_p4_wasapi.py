"""Unit tests for the P-4b WASAPI-probe pure core. No device, no PortAudio.

The probe's sounddevice import is lazy (inside the device layer), so importing the
module and exercising the ms math / gate branch / arg parse / --dry-run never
opens an audio device or pulls PortAudio (spec §10/§11).
"""
import measure_p4_wasapi as w


# --------------------------------------------------------------------------- #
# latency_ms / frames_to_ms - the unit conversions.
# --------------------------------------------------------------------------- #
def test_latency_ms_seconds_to_ms():
    assert w.latency_ms(0.032) == 32.0
    assert w.latency_ms(0.05) == 50.0
    assert w.latency_ms(None) is None               # missing stays missing


def test_frames_to_ms():
    # 480 frames @ 24kHz = 20ms.
    assert w.frames_to_ms(480, 24000) == 20.0
    assert w.frames_to_ms(0, 24000) is None
    assert w.frames_to_ms(480, 0) is None


# --------------------------------------------------------------------------- #
# wasapi_ruling - the <=50ms gate (spec §9).
# --------------------------------------------------------------------------- #
def test_wasapi_ruling_confirmed_at_or_under_gate():
    assert "CONFIRMED" in w.wasapi_ruling(32.0)
    assert "CONFIRMED" in w.wasapi_ruling(50.0)     # boundary: <=50 confirms


def test_wasapi_ruling_over_budget():
    r = w.wasapi_ruling(64.0)
    assert "OVER BUDGET" in r
    assert "exclusive" in r.lower()                 # names the FR-14 trap it must NOT take


def test_wasapi_ruling_none():
    assert "no latency" in w.wasapi_ruling(None)


# --------------------------------------------------------------------------- #
# format_ruling_block - shape + the honesty flags present.
# --------------------------------------------------------------------------- #
def test_format_ruling_block_has_key_lines():
    meta = {
        "date": "2026-08-03T10:00:00+05:00", "label": "mains",
        "device": "Speakers", "host_api": "Windows WASAPI", "samplerate": 24000,
        "frame_ms": 20, "channels": 1, "negotiated_ms": 32.0,
        "block_ms": "20.0ms", "dev_low_ms": "30.0ms", "dev_high_ms": "100.0ms",
    }
    out = w.format_ruling_block(meta)
    assert "GATE: P-4b" in out
    assert "shared/event-driven" in out
    assert "negotiated" in out.lower()
    assert "CONFIRMED" in out                        # 32ms <= 50


# --------------------------------------------------------------------------- #
# parse_args - defaults and overrides.
# --------------------------------------------------------------------------- #
def test_parse_args_defaults():
    a = w.parse_args([])
    assert a.device == "default"
    assert a.frame_ms == 20
    assert a.samplerate == 0                          # 0 = the device's WASAPI mix rate
    assert a.channels == 1
    assert a.label == ""
    assert a.dry_run is False


def test_parse_args_overrides():
    a = w.parse_args(["--device", "Speakers", "--frame-ms", "10",
                      "--samplerate", "48000", "--label", "battery", "--dry-run"])
    assert a.device == "Speakers"
    assert a.frame_ms == 10
    assert a.samplerate == 48000
    assert a.label == "battery"
    assert a.dry_run is True


# --------------------------------------------------------------------------- #
# --dry-run - offline smoke: exit 0, ruling block, no device opened.
# --------------------------------------------------------------------------- #
def test_dry_run_exits_zero_without_device(capsys):
    rc = w.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "GATE: P-4b" in out
    assert "CONFIRMED" in out                        # synthetic 32ms
    assert "no device opened" in out.lower()


def test_live_run_refuses_without_label(capsys):
    rc = w.main([])                                  # no --label, not dry-run
    err = capsys.readouterr().err
    assert rc == 2
    assert "label is REQUIRED" in err
