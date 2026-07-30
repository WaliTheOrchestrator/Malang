"""Put scripts/ on sys.path so tests can import the hand-run probes' pure cores.

The probes live in scripts/ (not an installed package) because they are one-off
measurement tools, not part of the runtime. Their pure helpers are still worth
unit-testing, so we make them importable here. Importing a probe module never
touches its engine/SDK - those imports are lazy, inside the engine layer.
"""
import pathlib
import sys

_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
