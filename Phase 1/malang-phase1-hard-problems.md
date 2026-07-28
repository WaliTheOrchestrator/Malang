# Malang Phase 1 — Hard Engineering Problems

*The problems that will actually hurt during the build, in rough order of pain. Each: what it is, why it's hard, and the basic approach to care for it. References: `malang-phase1-spec.md`, `malang-phase1-design.md`.*

---

## HP1. Echo — Malang hearing his own voice

**Problem:** The mic picks up Kokoro's output from the speakers. VAD reads it as user speech → Malang barges in on himself, or his own words end up transcribed as Waleed's turn (poisoning the log).
**Why hard:** Windows has no reliable system-level acoustic echo cancellation you can just call; laptop mic/speaker proximity makes it worse; headphones solve it but can't be assumed.
**Basic solution (v1.2 — upgraded from heuristic to real AEC):** WebRTC APM/AEC3 (`livekit.rtc.apm`) as the *primary* mechanism, running on capture before VAD/wake/STT, with every output frame fed to `process_reverse_stream()` as reference. An energy/correlation heuristic is not echo cancellation — it fails in both directions (self-barge-in or deafness-while-speaking), and even successful barge-ins leave Kokoro's own words contaminating Waleed's transcript. The correlation guard survives only as a third-layer sanity check. Half-duplex is no longer a fallback — it's the failure state the AEC exists to prevent. Test with speakers, not headphones, from day one; the M3b exit test is barge-in at normal volume with clean transcripts.

## HP2. End-of-turn detection (endpointing)

**Problem:** Deciding "Waleed has finished speaking" from ~300ms of silence. Thoughtful mid-sentence pauses trigger false endpoints (Malang interrupts); waiting longer kills latency.
**Why hard:** It's a prediction about intent, not a signal-processing fact. Every voice agent's most-tuned knob.
**Basic solution:** Combine VAD silence with *semantic* completeness — the Moonshine interim text tells you if the utterance looks finished (trailing "and…", "so…", question shapes). Make the threshold adaptive: longer wait after clause-final connectives, shorter after clear questions. Keep it a config value; expect to tune it for weeks. Log every endpoint decision + whether Waleed immediately continued (that's your training data for tuning).

## HP3. Cancellation correctness (the race conditions)

**Problem:** At any moment a turn may be killed by barge-in, preemption re-fire, timeout, or session close — while STT is streaming, an LLM call is in flight, and TTS is mid-sentence. Orphaned tasks answer questions nobody asked; double-cancels crash; a late LLM token arrives after the next turn started.
**Why hard:** Three concurrent streams with independent lifetimes; asyncio cancellation is cooperative, not instant.
**Basic solution:** One authority: the session state machine owns all transitions; everything else obeys. Every piece of in-flight work carries a `turn_id`; any output arriving with a stale `turn_id` is dropped at the boundary (one `if`, everywhere). Cancellation is idempotent. Write the chaos tests (spec §8) early, not at M6.

## HP4. Real-time audio in Python

**Problem:** Buffer underruns, callback jitter, GIL stalls → clicks, dropped audio, drifting latency.
**Why hard:** Python's GIL + garbage collection vs. a hard 10ms audio callback deadline.
**Basic solution:** The audio callback does nothing but move bytes to/from ring buffers — no allocation, no locks, no logging. All inference in executor threads reading from the rings. Monitor xrun counts as a first-class metric in the daily one-liner. If Python truly can't hold the deadline on this laptop, the capture/playback shim can become a tiny native helper — but try the ring-buffer discipline first; it usually suffices.

## HP5. Wake word in a real room

**Problem:** Bench accuracy ≠ home accuracy. TV, family voices, Urdu/Pashto phonemes resembling "Malang", fan noise — false wakes erode trust fast (spec A-2: ≤1/day).
**Why hard:** Your acoustic environment is unique and unlabeled; the model was trained on synthetic data.
**Basic solution:** Collect false wakes from day one (every `false_wake` session saves its trigger audio) and periodically retrain with them as hard negatives — livekit-wakeword supports this loop directly. Tune threshold on *your* recordings, not the paper numbers. Expect two or three retrain cycles before it settles.

## HP6. Sentence-streamed TTS that doesn't sound chopped

**Problem:** Synthesizing sentence-by-sentence for latency means prosody resets at every boundary; the reflex-clip → real-answer seam can sound like two recordings glued together.
**Why hard:** Kokoro has no cross-sentence prosody context; the seam is exactly where the listener is paying most attention.
**Basic solution:** Feed TTS at clause/sentence boundaries chosen by the segmenter (never mid-clause), keep one sentence of synthesis lookahead, and crossfade ~80ms at the reflex→answer seam. Author reflex clips to *end* on an open intonation (a lift, not a full stop) so continuation sounds natural. Accept imperfection: consistency of voice matters more than perfect prosody.

## HP7. Preemptive generation without burning money — *demoted in v1.2: not built by default*

**Status change:** the panel review demoted this feature to a measured contingency. Its savings land behind the reflex clip (which owns perception), it multiplies the chaos matrix, and its trigger breaks on short turns. What ships is the logging half only (interim/final divergence + hypothetical savings). Build gate: measured p50 >1.3s after M4. The problem below remains documented for that contingency.

**Problem:** Firing the LLM on interim transcripts wins 300–500ms but wrong interims mean cancelled, paid-for generations.
**Why hard:** The trigger ("transcript stable + endpoint likely") is probabilistic; too eager = waste, too shy = no benefit.
**Basic solution:** Fire only when the interim has been stable for N ms *and* VAD reports high endpoint probability. Count wasted generations per day (design D-7); auto-disable above 30% waste. Remember the ordering rule: T2 memory retrieval (Phase 2) must complete before the preemptive fire — build the trigger as a small pipeline, not an ad-hoc callback.

## HP8. Windows audio device chaos

**Problem:** Default device switches (headphones plugged in, Bluetooth connects), sleep/resume invalidating streams, exclusive-mode apps stealing the device — each silently kills the mic.
**Why hard:** Failures are asynchronous OS events, not exceptions in your call stack; some manifest only as silence.
**Basic solution:** Treat the audio stream as a supervised resource: a watchdog notices no-frames-for-2s and rebuilds the stream against the current default device with backoff. Every rebuild logged; if a session was live, close it cleanly (`error` reason) rather than limping. Test the top three cases by hand: unplug, Bluetooth, sleep.

## HP9. Crash-safe logging that is actually crash-safe

**Problem:** "Append-only JSONL, flushed per event" still loses data if the OS buffers writes, or leaves torn half-lines on power loss — and the whole system's value rests on the record (spec: the Scribe is sovereign).
**Why hard:** fsync semantics on Windows/NTFS are easy to get subtly wrong; you find out during the one crash that mattered.
**Basic solution:** One writer thread; `flush()` + `os.fsync()` per event; recovery tolerates a torn final line (drop it, it's at most one event). WAV written in chunks with a header fix-up on close, and the recovery pass finalizes orphaned WAVs. Then actually test it: `kill -9`, power-button hold, mid-write. A-12 exists for this — run it early, not at acceptance.

## HP10. Latency honesty (measuring what Waleed feels)

**Problem:** It's easy to measure component latencies that sum to a number nobody experiences; perceived latency (endpoint → first audible sound *from the speaker*) includes audio output buffering, OS mixing, and your own queuing.
**Why hard:** The gap between internal timestamps and acoustic reality can be 100–200ms of invisible loss.
**Basic solution:** Instrument end-to-end at the edges: timestamp the last mic sample of the user's turn and the first sample actually handed to the output device; spot-check acoustically (record mic+speaker with a phone, measure the real gap) once per milestone. Percentiles in the daily one-liner, p95 not just p50 — presence is judged by the worst turns.

## HP11. Prompt-cache discipline

**Problem:** The cost model assumes ~90% cached input on the persona block. One byte of drift in the cached prefix (a timestamp, reordered context) silently invalidates the cache and triples your bill.
**Why hard:** Caches fail silently — everything works, just costs more.
**Basic solution:** Strict prompt block ordering (static persona first, volatile context last); never interpolate anything time-varying into block 1; assert cache-hit tokens in the API response per call and alarm in the daily one-liner if the hit rate drops below ~80%.

---

## v1.1 amendment problems (the price of the 1.4s → 1.1s budget)

## HP12. Two probabilistic triggers stacked — semantic endpointing × preemptive generation

**Problem:** v1.1 adds a semantic turn-detector on top of silence VAD, and preemptive generation already fires on "probable endpoint." Now two probabilistic systems chain: a wrong semantic "he's done" both cuts Waleed off mid-thought AND fires a paid LLM call on a half-sentence. Errors don't add — they multiply, and the failure *feels* like being interrupted by someone who wasn't listening.
**Why hard:** Each system is tuned separately but they share a trigger; tuning one shifts the other's optimum. And the semantic model was trained on other people's speech, not a Pashtun engineer's English thinking-pauses.
**Basic solution:** The spec's rule is load-bearing — semantic may never close a turn without the silence gate agreeing (D-9); it can only *shorten* the wait, never override the ears. Log every endpoint decision with ground truth (did he keep talking?) and every preemption with waste outcome — one weekly review tunes both against the same log. Kill-switch to pure silence costs only 150ms; use it without shame during bad weeks. Expect 2–3 weeks of tuning before trusting it; the spec budget already assumes the *tuned* state, so measure A-3/A-4 only after tuning settles.

## HP13. The fast TTS chain — int8 voice drift and clause-joint prosody

**Problem:** Two speed upgrades touch the one thing that IS Malang's presence: the voice. int8 quantization can subtly flatten timbre (worst on emotional range, exactly where presence lives), and starting synthesis at the first comma means joining audio segments the model never planned as one utterance — audible seams, pitch resets mid-sentence.
**Why hard:** Both degradations are gradual and subjective — no metric catches "he sounds slightly less alive"; you just stop enjoying talking to him and won't know why.
**Basic solution:** P-4's blind A/B listening check is the gate — ears, not benchmarks, and re-run it after any model or runtime update. Join rules: never split mid-clause, crossfade ≥60ms, and prefer splitting after clauses that end in a natural pitch fall (the segmenter can approximate this from punctuation). If clause-joins fail the ear test, fall back to sentence-level and pay the +100ms honestly — a voice that sounds whole at 1.2s beats a seamy one at 1.1s. Presence outranks the stopwatch; that ordering is the whole Phase 1 thesis.

## HP14. WASAPI low-latency mode vs. the rest of Windows

**Problem:** Event-driven/exclusive WASAPI buys back ~80ms, but low-latency audio on Windows is a compatibility minefield: exclusive mode blocks every other app's sound (and they block Malang), some drivers misreport buffer capabilities, Bluetooth devices renegotiate on their own schedule, and sleep/resume can leave an event-driven stream half-alive in ways shared mode tolerates.
**Why hard:** It works perfectly on the dev machine until the day it doesn't, and the failure is silence with no exception — the hardest class of bug from HP8, now with stricter timing.
**Basic solution:** Shared-mode event-driven as the default (most of the win, far fewer conflicts); exclusive mode strictly opt-in config. Probe device capabilities at startup and *log the negotiated buffer size* — if the driver hands back a fat buffer, the daily one-liner should say so rather than silently eating the latency budget. Fold WASAPI failures into HP8's watchdog (no-frames-for-2s → rebuild stream, fall back to shared/default mode, never die). Budget assumes ≤50ms p95; if a device can't deliver it, record the honest number and move on — 30ms of output buffer is not worth a fragile audio stack.

---

---

## v1.2 panel problems (found by four adversarial reviewers; accepted by the architect)

## HP15. The wake word doesn't know Waleed's mouth — or his music

**Problem:** livekit-wakeword's default training generates positives with English TTS voices pronouncing "Malang" as English; the model tunes to a pronunciation nobody in the house uses. Worse: "Malang" occurs *correctly pronounced* in Pashto/Urdu songs and a Bollywood title — if music plays, that's a true positive from the wrong source, and no threshold fixes it.
**Why hard:** Training-data mismatch is invisible until the A-1/A-2 bench fails, and the tempting fix (drop the threshold) trades misses for false wakes.
**Basic solution:** Train on the real mouth — 100–200 recordings of Waleed (and anyone else who'll summon him: now or never) across distances, noise, and tiredness; accent-matched synthetics; hard negatives including near-words AND a folder of the house's actual music. New M2 bench: 2 hours of Pashto/Urdu playlists at room volume, zero wakes.

## HP16. Kokoro's first chunk IS the latency

**Problem:** Kokoro synthesizes an entire chunk before the first sample exists — a 2-second first clause means ~1 second of dead air, and per-call overhead makes tiny texts *relatively* slower (RTF ~0.7 on short strings vs ~0.5 on long).
**Why hard:** The v1.1 budget assumed vocoder-style streaming; the error only shows on a stopwatch, and it moved the honest voice-to-voice baseline from ~1.1s to ~1.3s.
**Basic solution:** Micro-first-chunk rule ({comma | 5–7 words | ~350ms audio}), pre-warmed session, ahead-buffering that includes the *first* chunk, selective int8 (blind quantize_dynamic = audible static), and the misaki lexicon so the presence can say its own name. Re-baseline accepted in daylight; perception unaffected — that's the reflex tier's job.

## HP17. The cache that defeats itself

**Problem:** Prompt caching is strictly prefix-based; one mutating token in system block 2 (the old "session summary so far") invalidates block 3 and the entire message history, every turn — the v1.1 TTFT lever quietly dead on arrival.
**Why hard:** Caches fail silently; everything works, just slower and pricier, and only the cached-tokens field in the API response tells the truth.
**Basic solution:** Block 2 is per-session static (date/time + continuity line, computed once at open); per-turn context rides in the newest user message; second cache breakpoint at history tail. Assert cache-hit ratio ≥80% in the M4 exit test and alarm in the one-liner below that.

## HP19. AEC's hard half is delay alignment, not integration (v1.3)

**Problem:** AEC3's adaptive filter needs the reference signal time-aligned with what actually left the speakers. PortAudio tells you when a frame was *queued* — acoustic emission differs by WASAPI buffer depth + driver latency + any Bluetooth transport delay, and that offset *changes* on device switch and after suspend/resume. Misalign beyond the filter length and AEC3 degrades toward pass-through — silently, while the code looks correct and the logs look clean, reproducing the exact self-barge-in it was installed to prevent.
**Why hard:** The failure has no error state. Everything runs; the echo just stops being cancelled.
**Basic solution:** Measure the capture↔render offset at startup and after every device-change/resume event; feed it via the APM stream-delay API; log the value ("AEC delay estimate" in the one-liner — drift is the early warning). M3b exit gains an ERLE probe: play a known tone through the speakers with nobody talking, measure the residual in the cleaned stream — a number, not a vibe. Re-run the probe inside M6's Bluetooth chaos case.

## HP18. Day-4 amnesia — the failure the diagnosis clause couldn't see

**Problem:** A companion with zero cross-session memory re-asks and re-forgets everything; by day 4–5 the user unconsciously stops asking anything that requires continuity, and the presence test fails — while the failure analysis points at latency, because memory was defined out of phase.
**Why hard:** It's a *diagnostic* trap more than a technical one: the wrong suspect list sends weeks at the wrong problem. Amnesia is the strongest "program" tell that exists.
**Basic solution:** The capped continuity line (FR-17): ≤100 tokens of yesterday, Afterword-written, one string at session open, kill-switch for A/B. And the rewritten soft-criterion clause: suspect order is amnesia → latency → session model. The rule that survives: the Session Engine reads nothing from `memory/` — one string at open is the entire exception, and Phase 2 may delete the mechanism.

---

*Rule of thumb across all of these: every one is testable on the real laptop with the real mic in the real room — bench numbers and simulated audio will lie to you. The daily one-liner (latency percentiles AC/DC-split, xruns, false wakes, cache hit rate, endpoint miss rate, reflex play counts, negotiated buffer size, cost) is the cheapest early-warning system you can build; build it first. The v1.1 lesson: every millisecond bought must pass an ear test. The v1.2 lesson: the fittings below the waterline — echo, durability, identity — don't show up on the blueprint's beauty; they show up at sea. Seal them in dry dock.*
