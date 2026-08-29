# Test plan — Pi + ReSpeaker v2.0 (TLV320AIC3104) enclosure / PipeWire AEC

Two symptoms to explain:

- **S1** — AEC removes far more than the echo: over half the near-end speech disappears.
- **S2** — Added noise and whistles in the AEC output.

They may have the same root cause or two different ones. The plan is ordered so that
each phase eliminates whole branches. **Do not skip ahead**: several later phases are
meaningless if an earlier one hasn't been cleared, and tuning suppression on top of a
broken linear filter is the classic way to spend a week going in circles.

Tools: `enclosure_probe.py` (echo path physics), `aec_score.py` (end-to-end KPIs).

---

## Rules for the whole campaign

1. **One variable per run.** Never change the enclosure and the config in the same step.
2. **Freeze the rig.** Tape-mark the talker speaker position, the enclosure position,
   and the surface it stands on. Record every level in the log. A run taken with
   different geometry is not comparable to anything.
3. **Log everything** in `runs/<tag>/` with a one-line note on what changed.
4. **Re-run the previous best config** every ~10 runs as a drift check. If it no longer
   reproduces, something in the rig moved and the intervening results are suspect.
5. Never measure S1/S2 by ear as the primary signal. Ears are for noticing; the
   numbers are for deciding.

### Headline KPIs (from `aec_score.py`)

| KPI | Meaning | Target | Fail |
|---|---|---|---|
| `erle_db` | echo attenuation, far-end single-talk | > 30 | < 20 |
| `retention_db` | near-end speech surviving double-talk | > −3 | < −8 |
| `whistle_index` | musical-noise indicator | < 2 | > 4 |

`retention_db` is the number that corresponds to S1. `whistle_index` corresponds to S2.

---

## Phase 0 — Build the rig and get a baseline

**Goal:** make the problem measurable before touching anything.

1. Obtain a second, **wired** speaker as the artificial talker (cheap USB speaker;
   Bluetooth is unusable, its latency wanders). Fix it 50 cm from the enclosure, tape-marked.
2. Identify all four PipeWire nodes:
   ```bash
   pw-cli ls Node | grep -E "node.name|node.description"
   ```
   You need: the AEC sink, the AEC source, the raw `seeed2micvoicec` input, the talker output.
3. Force unity gain on both capture nodes so raw and AEC paths are comparable:
   ```bash
   wpctl set-volume <raw-source-id> 1.0
   wpctl set-volume <aec-source-id> 1.0
   ```
4. Baseline run, current config untouched:
   ```bash
   python3 aec_score.py run --tag 00-baseline \
     --enclosure-out <aec-sink> --talker-out <usb> \
     --in-aec <aec-source> --in-raw <raw-source>
   ```
5. Save `mixer_dump.txt`, your PipeWire conf, `pw-top` output, and `uname -a`.

**Gate 0:** you now have `erle_db`, `retention_db`, `whistle_index`. Everything
afterwards is judged against these three numbers.

- If `erle_db` is already > 30 and only `retention_db` is bad → the linear filter is
  fine and this is purely a suppression/NS/AGC tuning problem. **Jump to Phase 5**,
  then come back to Phase 3 only if Phase 5 can't fix it.
- Otherwise continue in order.

---

## Phase 1 — Is it even acoustic?

**Goal:** rule out electrical noise before spending any effort on the enclosure.
S2 in particular has a strong electrical candidate.

Run `enclosure_probe.py silence` in each condition, 30 s each:

| Run | Condition |
|---|---|
| 1a | Everything normal, nothing playing |
| 1b | Speaker unplugged from the JST connector |
| 1c | APA102 LEDs driven off / their driver disabled |
| 1d | Pi under heavy CPU load (`stress-ng --cpu 4`) |
| 1e | Pi on battery / different PSU, WiFi disabled |

Compare the listed narrowband tones across runs.

**Gate 1:**
- **Tones present in 1a and unchanged in 1b** → not acoustic. The whistles are EMI or
  supply noise coupling into the mic preamps. → **Branch E** below. S2 is solved
  there and you return to Phase 2 for S1 only.
- **Tones present in 1a, gone in 1b** → the amplifier or its supply is the source
  (switching noise, or the amp self-oscillating into a reactive load). → **Branch E**.
- **Tones appear only in 1c or 1d** → LED driver or CPU/DC-DC coupling. → **Branch E**.
- **No tones anywhere; floor is broadband and low** → S2 is genuinely being *created*
  by the AEC's noise suppressor. Continue to Phase 2; expect Phase 5 to fix S2.

> **Branch E (electrical):** separate the analogue ground return of the speaker from the
> mic ground; add series ferrite and an RC snubber at the speaker terminals; keep speaker
> wiring away from the mic traces and out of parallel runs; power the Pi from a linear
> supply for the duration of the test to confirm. Re-run 1a until clean, then rejoin at Phase 2.

---

## Phase 2 — Codec configuration audit

**Goal:** eliminate the AIC3104's own processing, which can defeat an AEC entirely.

1. `amixer -c seeed2micvoicec contents > mixer_dump.txt`
2. Disable the hardware AGC/ALC on both ADC channels. Look for `AGC`,
   `AGC Target Level`, `AGC Max PGA`, `AGC Attack/Decay Time`, `ALC`.
3. Mute every analogue bypass into the output mixers (`Line2L → HPLOUT`,
   `PGA → LOP`, `LINE1L Playback`, etc.). Only `DAC → Output Mixer` stays live.
4. Disable de-emphasis and any digital effects biquads in the DAC path.
5. Set the mic PGA to a **fixed** value. Pin the sample rate to 48 kHz on both the
   card and PipeWire (`default.clock.allowed-rates = [ 48000 ]`).
6. `alsactl store`, restart PipeWire, re-run `aec_score.py run --tag 02-codec-clean`.

**Gate 2:**
- **`retention_db` improves by more than 4 dB** → the hardware AGC was the primary
  cause of S1. A time-varying, undeclared mic gain makes the adaptive filter
  unconvergeable. Confirm by re-enabling it alone and watching the number go back.
  Then re-baseline and reconsider whether Phases 3–4 are still needed.
- **`erle_db` improves sharply** → you had an analogue bypass path competing with the
  acoustic one and confusing the delay estimator.
- **Nothing changes** → continue to Phase 3.

---

## Phase 3 — Linearity vs. drive level

**Goal:** find the level at which the output stage or driver stops being linear.
This caps ERLE no matter what you do in software, and is my leading hypothesis.

```bash
for A in 0.03 0.06 0.12 0.25 0.5 0.8; do
  python3 enclosure_probe.py sweep --amp $A --out lvl_$A \
    --in-dev <raw> --out-dev <raw>
done
```

Plot `harmonic_to_linear_db["2"]` and `["3"]` against amplitude.

**Gate 3:**
- **A clear knee exists** (distortion rises steeply past some amplitude) → set your
  operating level 6 dB below the knee, re-run `aec_score.py --tag 03-level-backoff`,
  and see how much of S1 that alone recovers. This is a free fix — no hardware change.
- **Harmonics worse than −25 dB even at 0.03** → something is distorting at all levels:
  ADC clipping (lower the PGA and repeat), a mechanical rattle, or the driver being
  driven through a DC-blocking capacitor that's too small. Investigate before continuing.
- **Harmonics better than −35 dB across the range** → linearity is fine, the echo path
  is not the problem. **Skip Phase 4's damping work** and go to Phase 4 for the tail
  measurement only, then to Phase 5.

Also note whether backing off the level changes `whistle_index`. If it does, S2 is
downstream of distortion, not an independent problem.

---

## Phase 4 — Echo path structure

**Goal:** characterise the tail and find out which mechanical part causes it.
Run everything at the operating level fixed in Phase 3.

### 4.1 Baseline path

```bash
python3 enclosure_probe.py sweep --amp <operating> --out 04-assembled
python3 enclosure_probe.py noise --amp <operating>
```

Record: `bulk_delay_ms`, `erl_db`, `t20_ms`, `t30_ms`, `band_erl_db`, coherence per band.

**Gate 4.1:**
- `t30_ms` < 40 **and** coherence > 0.97 across 300–3400 Hz → the enclosure is not your
  problem. **Skip 4.2 and Phase 6 entirely** and go to Phase 5.
- `t30_ms` > 60 → the tail exceeds what AEC3's adaptive filter covers. Damping work is
  mandatory; continue to 4.2.
- Coherence dips in a narrow band → note the frequencies, they'll match the bumps in
  `band_erl_db` and identify which resonator is responsible.

### 4.2 Path decomposition

Four sweeps, identical level, identical mic gain:

| Run | Configuration | Isolates |
|---|---|---|
| 4.2a | Fully assembled (= 4.1) | reference |
| 4.2b | Top half detached, on foam, 200 mm away, wires extended | pure airborne |
| 4.2c | Assembled, TPU legs replaced with soft foam blocks | the legs' contribution |
| 4.2d | Assembled, ReSpeaker PCB on silicone grommets inside the dome | board mounting |

Compute per-band deltas (a−b), (a−c), (a−d).

**Gate 4.2** — attribute the tail:
- **(a−c) large, especially 100–400 Hz** → the TPU legs are transmitting, and probably
  resonating rather than isolating. → Phase 6 item *legs*.
- **(a−b) large above 1.5 kHz with narrow peaks** → the steel ring and/or dome are
  ringing. → Phase 6 items *ring damping*, *dome lining*.
- **(a−d) large** → the PCB is rigidly coupled; cheapest fix in the whole project.
  → Phase 6 item *PCB isolation*.
- **All deltas small but `t30` still high** → the ring-down is inside the sealed
  bottom volume, i.e. it's the box itself. Add internal damping material to the baffle
  enclosure.

---

## Phase 5 — PipeWire, one knob at a time

**Goal:** find the minimum processing that meets the KPIs. Do this **after** the
physical path is as good as it's going to get, or the tuning will be optimised for a
problem you're about to change.

Start from AEC-only: `noise_suppression=false`, `gain_control=false`,
`analog_gain_control=false`, `digital_gain_control=false`, `voice_detection=false`,
`high_pass_filter=true`, `extended_filter=false`, `node.latency = 480/48000`.

| Run | Change |
|---|---|
| 5a | AEC only (above) |
| 5b | 5a + `high_pass_filter=false` |
| 5c | best of 5a/5b + `voice_detection=true` |
| 5d | best so far + `noise_suppression=true` |
| 5e | best so far + `digital_gain_control=true` |
| 5f | best so far + `extended_filter=true` |
| 5g | best so far, `node.latency = 960/48000` |

```bash
python3 aec_score.py compare 05a 05b 05c 05d 05e 05f 05g
```

**Gate 5:** keep a setting **only if it improves at least one KPI without degrading
another by more than 1 dB.** Expected pattern given your symptoms: 5d and 5e each cost
several dB of `retention_db`, and 5d raises `whistle_index` sharply. If so, S1 and S2
are both suppression artefacts and the answer is to leave NS and AGC off here and do
noise reduction downstream in a separate `module-filter-chain` where it can't interact
with the echo estimate.

If `erle_db` is still < 25 with everything off, the AEC is not converging and no
combination of these flags will help — go back to Phase 3/4 results.

---

## Phase 6 — Mechanical fixes

Only the items Gate 4.2 pointed at. **One at a time**, re-running 4.1 after each.

| Fix | Do it | Expect |
|---|---|---|
| Ring damping | butyl tape + thin constraining strip, or pot the inner channel | narrow `band_erl_db` peaks flatten; `t30` drops |
| PCB isolation | silicone grommets, board floating in the dome | broadband `t30` drop, best effort/benefit ratio |
| Dome lining | open-cell foam or wool felt against the inner wall | HF tail and cavity modes drop |
| Leg retune | thinner / hourglass-waisted legs, softer TPU (60–70A), or added top mass | LF transmission drops; target isolation resonance < 70 Hz |
| Leak check | smoke or soapy water around leg mounts at high excursion | removes level-dependent chuffing |

**Gate 6:** stop when `t30_ms` < 40 and coherence > 0.97 in 300–3400 Hz, or when a fix
returns less than 3 dB. Then **re-run Phase 5 from scratch** — the optimal software
settings change once the physical path changes.

---

## Phase 7 — Soak and regression

1. 30-minute continuous run; count xruns in `pw-top`.
2. Drift check: 10-minute simultaneous playback and capture, compare the sample offset
   of a click at the start and at the end. Should be ~0 (single codec, shared clock).
   Non-zero means something is resampling and must be found.
3. Re-convergence: stop and restart playback 20 times; measure how long `erle_db`
   takes to recover each time.
4. Thermal: repeat the Phase 0 baseline after an hour of running. PLA creeps and TPU
   softens; a fix that depends on leg stiffness may not hold.

---

## Reporting checkpoints

Stop and reassess the plan after each of these, rather than running straight through:

- **After Gate 0** — the three baseline numbers decide whether this is a hardware or a
  software campaign, and may let you skip Phases 3, 4 and 6 entirely.
- **After Gate 1** — decides whether S2 is a separate electrical problem.
- **After Gate 2** — the AGC result may end the investigation on its own.
- **After Gate 3** — a distortion knee gives you a free fix and re-frames everything after.
- **After Gate 4.2** — tells you which mechanical work is worth doing and which isn't.
- **After Gate 5** — if the KPIs are met, stop. Phase 6 is only worth doing if they aren't.
