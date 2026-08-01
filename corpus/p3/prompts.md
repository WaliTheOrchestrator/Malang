# P-3 corpus — what to record

Goal: **~30 minutes** of *your* speech on the **production mic**, in three
registers, so the bake-off measures the models on the voice, accent, room, and
device they will actually face. Record each register to its own file with
`python scripts/record_p3_corpus.py` (writes 16 kHz mono WAV under `audio/`).

Then **hand-correct** each `reference/*.txt` to exactly what you said, and tag the
proper nouns in `manifest.json`. The gate is only as honest as this reference
(spec section 12 rule 1).

Three rules that make the numbers valid (spec section 13 "validity failure"):
- **Real code-switching.** The code-switched passage must contain genuine
  Urdu/Pashto↔English switches, the way you actually speak — not English with one
  loanword. If it's flat English, every model "passes" on a flattering corpus.
- **Real proper nouns.** Say "Malang" and your actual family names, several times,
  across registers. Proper-noun-error-rate on these is the number that decides the
  hybrid, and it seeds the FR-18 vocab list.
- **Same you.** Normal pace, normal distance from the mic, the room you use.

---

## 1. `monologue` → `audio/monologue.wav`  (~10 min, unscripted)

Talk, unscripted, the way you'd talk to Malang. Suggested cues — wander freely:

- What you did today, and the one thing still on your mind about it.
- A decision you're turning over, out loud, both sides of it.
- Describe someone in your family and a specific memory with them (use their real
  name — this is one of the proper-noun sources).
- Explain this project to an imaginary friend: what Malang is, why the record matters.

Naturally use the name **Malang** and at least two real family names here.

## 2. `read` → `audio/read.wav`  (~10 min, read aloud)

Read a fixed passage aloud, at a normal pace. Use any book/article you like **and
paste exactly what you read into `reference/read.txt`** — or read the passage below
(it's already in `reference/read.txt` as a starting point; replace it if you read
something else). A read passage gives a clean, unambiguous reference and isolates
acoustic/accent effects from disfluency.

## 3. `codeswitch` → `audio/codeswitch.wav`  (~10 min, deliberately mixed)

Speak the way you do when you slip between languages — tell a story, give someone
directions, recount a conversation — mixing Urdu/Pashto and English **naturally and
often**. Weave in **Malang** and family names repeatedly (this is the deciding
passage). Don't perform "textbook" sentences; the point is your real cadence, which
is exactly what a code-switched proper-noun error rate is meant to catch.

---

After recording: correct `reference/*.txt`, fill `proper_nouns` in `manifest.json`
with the real names you used, then run
`python scripts/measure_p3_stt.py --corpus corpus/p3 --models all`.
