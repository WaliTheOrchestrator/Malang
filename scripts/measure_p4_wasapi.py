#!/usr/bin/env python3
"""P-4b measurement gate: shared-mode event-driven WASAPI output-buffer latency.

Spec: .claude/specs/p-4-selective-int8-ear-check-wasapi-probe.md (§9, §12 rule 6).

The §5 budget claims the audio output path is 30-40ms p50 / 50ms p95 on a
shared-mode event-driven WASAPI stream. HP14 warns a driver may silently hand back
a fat buffer, so we do not assume - we open the stream and read the NEGOTIATED
latency PortAudio reports (`Stream.latency`, from Pa_GetStreamInfo()->outputLatency,
the negotiated not the requested value). Gate: <=50ms -> confirmed.

    uv run python scripts/measure_p4_wasapi.py --label mains        # built-in speakers
    uv run python scripts/measure_p4_wasapi.py --label battery      # cheap spot-check
    uv run python scripts/measure_p4_wasapi.py --dry-run            # no device

Honesty rules kept (spec §12 rule 6):
  - Measure the NEGOTIATED buffer, never the requested one (HP14).
  - Shared mode only (WasapiSettings(exclusive=False)); event-driven is PortAudio's
    default and only reachable mode. Exclusive is NOT adopted to force <=50ms - it
    is an FR-14 violation (§5 rejection).
  - Built-in speakers only; a Bluetooth/USB device is a DIFFERENT measurement (§3).
  - This is the API/driver buffer, NOT the phone-recorded acoustic path (HP10) -
    the end-to-end perceived number is M3a/M3b's.
  - PortAudio documents a shared-mode WASAPI floor of ~20ms; the 30-40/50ms budget
    sits only ~10-20ms above it - modest headroom, state it (§6).

The `sounddevice` import is lazy so the pure core, --dry-run, and the unit tests
need no PortAudio (spec §10/§11 - it lives in the `p4` extra, not base).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys

GATE_MS = 50.0                     # §5 p95 ceiling for the output path
DEFAULT_SAMPLERATE = 24000         # Kokoro's native rate (resample is M3a's)
DEFAULT_FRAME_MS = 20              # §5 frame size


# --------------------------------------------------------------------------- #
# Pure core - no device, unit-tested.
# --------------------------------------------------------------------------- #
def latency_ms(seconds):
    """PortAudio reports latency in seconds; the gate is in ms. None stays None."""
    return None if seconds is None else seconds * 1000.0


def frames_to_ms(frames, samplerate):
    """Buffer size in frames -> ms, for context alongside the reported latency."""
    if not frames or not samplerate:
        return None
    return frames / samplerate * 1000.0


def wasapi_ruling(negotiated_ms, gate=GATE_MS):
    """The pre-decided gate branch (spec §9) for a negotiated output latency."""
    if negotiated_ms is None:
        return "no latency recorded - the stream did not report one"
    if negotiated_ms <= gate:
        return (f"CONFIRMED (negotiated output latency {negotiated_ms:.1f}ms <= "
                f"{gate:.0f}ms) - the §5 audio-output budget holds on this device")
    return (f"OVER BUDGET (negotiated {negotiated_ms:.1f}ms > {gate:.0f}ms). Record it "
            "honestly (HP14): revise the §5 output budget or flag the device in the "
            "one-liner. Do NOT adopt exclusive mode to force it green (FR-14).")


def format_ruling_block(meta):
    """The /measure ruling shape for P-4b, ready to paste into docs/."""
    neg = meta.get("negotiated_ms")
    lines = [
        "GATE: P-4b (shared-mode event-driven WASAPI output buffer)",
        f"DATE / CONDITIONS: {meta.get('date')} | machine=i3-1315U | "
        f"label={meta.get('label')} | device={meta.get('device')!r}",
        f"    host_api={meta.get('host_api')} | mode=shared/event-driven | "
        f"samplerate={meta.get('samplerate')} | frame_ms={meta.get('frame_ms')} | "
        f"channels={meta.get('channels')}",
        "RAW NUMBERS:",
        f"    negotiated output latency: "
        f"{'n/a' if neg is None else f'{neg:.1f}ms'}  (Stream.latency, the negotiated "
        "value - HP14)",
        f"    requested block:           {meta.get('block_ms', 'n/a')}",
        f"    device default low/high:   {meta.get('dev_low_ms', 'n/a')} / "
        f"{meta.get('dev_high_ms', 'n/a')}  (context only)",
        f"    PortAudio shared-mode floor ~20ms (§6) - headroom to the 50ms gate is modest",
        f"RULING:            {wasapi_ruling(neg)}",
        "CONSEQUENCE:       confirms (or revises) the §5 shared-mode output-path budget "
        "M3a's WASAPI stage is graded against; keeps audio.output.exclusive=false the "
        "standing default. This is the driver buffer, NOT the acoustic path (HP10/M3b).",
        "REVERSED BY:       a different output device (Bluetooth/USB negotiates its own "
        "buffer), a driver update, or the battery/power-throttled run.",
    ]
    return "\n".join(lines)


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="measure_p4_wasapi.py",
        description="P-4b: measure the negotiated shared-mode WASAPI output buffer.",
    )
    p.add_argument("--device", default="default",
                   help="Output device (default: %(default)s = built-in speakers). A "
                        "non-built-in device is a different measurement (§3).")
    p.add_argument("--frame-ms", type=int, default=DEFAULT_FRAME_MS,
                   help="Requested block size in ms (default: %(default)s).")
    p.add_argument("--samplerate", type=int, default=0,
                   help="Stream sample rate; 0 (default) = the device's WASAPI "
                        "shared-mode mix rate, which is what the real output path runs "
                        "at (shared mode rejects arbitrary rates). State what was used.")
    p.add_argument("--channels", type=int, default=1,
                   help="Output channels (default: %(default)s - the 16k-mono contract).")
    p.add_argument("--label", default="",
                   help="REQUIRED on a live run: mains or battery (§12 rule 6).")
    p.add_argument("--dry-run", action="store_true",
                   help="Offline: exercise the ms math + gate branch, open no device.")
    return p.parse_args(argv)


# --------------------------------------------------------------------------- #
# Device layer - hand-run only, lazily imports sounddevice.
# --------------------------------------------------------------------------- #
def probe_negotiated_latency(device, samplerate, channels, frame_ms):
    """Open a shared-mode event-driven WASAPI output stream, read what it negotiated.

    Returns a meta dict. The stream is briefly started (event-driven negotiates on
    start) then closed; nothing audible is played beyond silence.
    """
    import numpy as np
    import sounddevice as sd

    extra = sd.WasapiSettings(exclusive=False)  # shared mode; event-driven is default
    blocksize = max(1, int(samplerate * frame_ms / 1000))

    # WasapiSettings can ONLY attach to a device on the WASAPI host API. PortAudio's
    # 'default' output resolves to MME on Windows (PaErrorCode -9984 otherwise), so
    # 'default' means "the WASAPI host API's default output" - the built-in speaker.
    if device in ("", "default"):
        wasapi = next((i for i, h in enumerate(sd.query_hostapis())
                       if "WASAPI" in h["name"]), None)
        if wasapi is None:
            raise RuntimeError("No 'Windows WASAPI' host API on this machine.")
        dev = sd.query_hostapis(wasapi)["default_output_device"]
        if dev is None or dev < 0:
            raise RuntimeError("The WASAPI host API reports no default output device.")
    else:
        dev = int(device) if str(device).isdigit() else device

    info = sd.query_devices(dev, "output")
    host_api = sd.query_hostapis(info["hostapi"])["name"]
    if "WASAPI" not in host_api:
        raise RuntimeError(
            f"Device {info['name']!r} is on {host_api!r}, not WASAPI - the shared-mode "
            "event-driven buffer measurement requires a WASAPI device (§3).")

    # WASAPI SHARED mode is locked to the device's mix-format rate (the Windows audio
    # engine's own rate) - requesting an arbitrary rate is PaErrorCode -9997. So we
    # measure at the rate the real shared output path actually runs at. `samplerate=0`
    # (the default) means "the device mix rate"; upstream resampling from Kokoro's
    # 24kHz is M3a's contract, not the device stream's. Record what was used.
    rate = int(samplerate) if samplerate else int(round(info["default_samplerate"]))
    blocksize = max(1, int(rate * frame_ms / 1000))

    stream = sd.OutputStream(
        samplerate=rate, channels=channels, dtype="float32",
        blocksize=blocksize, device=dev, extra_settings=extra,
    )
    with stream:
        stream.write(np.zeros((blocksize, channels), dtype="float32"))
        negotiated_s = stream.latency  # negotiated, not requested (HP14)

    return {
        "device": info.get("name"), "host_api": host_api, "samplerate": rate,
        "negotiated_ms": latency_ms(negotiated_s),
        "block_ms": f"{frames_to_ms(blocksize, rate):.1f}ms ({blocksize} frames @ {rate}Hz)",
        "dev_low_ms": f"{latency_ms(info.get('default_low_output_latency')):.1f}ms",
        "dev_high_ms": f"{latency_ms(info.get('default_high_output_latency')):.1f}ms",
    }


def _run_dry(args):
    meta = {
        "date": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "label": args.label or "(unlabelled dry-run)", "device": "Speakers (synthetic)",
        "host_api": "Windows WASAPI", "samplerate": args.samplerate or 48000,
        "frame_ms": args.frame_ms, "channels": args.channels,
        "negotiated_ms": 32.0, "block_ms": f"{args.frame_ms:.1f}ms (synthetic)",
        "dev_low_ms": "30.0ms", "dev_high_ms": "100.0ms",
    }
    print("[dry-run] no device opened - synthetic numbers.\n")
    print(format_ruling_block(meta))
    return 0


def _run_live(args):
    sys.stdout.reconfigure(encoding="utf-8")
    if not args.label:
        print("Refusing to run: --label is REQUIRED on a live run (mains or battery). "
              "A buffer number without a power source is not a valid P-4b record "
              "(spec §12 rule 6).", file=sys.stderr)
        return 2
    try:
        probed = probe_negotiated_latency(
            args.device, args.samplerate, args.channels, args.frame_ms)
    except ImportError as exc:
        print(f"sounddevice is not installed ({exc}). `uv pip install sounddevice` "
              "(the p4 extra). --dry-run works offline.", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - a device failure is a finding, not a crash
        print(f"Could not open a shared-mode WASAPI output stream on "
              f"{args.device!r}: {exc}\nDo not silently substitute another device - "
              "that is a different measurement (§3). Recording nothing.", file=sys.stderr)
        return 1

    meta = {
        "date": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "label": args.label, "samplerate": args.samplerate,
        "frame_ms": args.frame_ms, "channels": args.channels, **probed,
    }
    print(format_ruling_block(meta))
    print("\nPaste the block above into docs/m0-measurements.md (replace the P-4b "
          "stub). Run once on mains and once on battery (§12 rule 6).")
    return 0


def main(argv):
    args = parse_args(argv)
    if args.dry_run:
        return _run_dry(args)
    return _run_live(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
