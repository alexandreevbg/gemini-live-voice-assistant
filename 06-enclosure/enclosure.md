# Raspberry Pi Smart Speaker — Build Documentation

A spherical, full-duplex smart speaker built around a Raspberry Pi Zero 2W and a ReSpeaker 2-Mic HAT, with mechanical and acoustic design optimized for clean AEC (echo cancellation) at usable playback volumes.

## Design Goals

1. **Clean AEC at high volume** — the speaker should remain in its linear operating range across the useful volume range, so PipeWire's WebRTC AEC3 can maintain effective echo cancellation.
2. **Mic isolation from speaker vibration** — the microphones must hear room sound, not the enclosure's structural reaction to the driver.
3. **Adequate thermal dissipation** for the Pi SoC.
4. **Compact, aesthetically clean form** — spherical, with a clean visible parting line.

## Final Acoustic Architecture

| Decision | Choice | Rationale |
|---|---|---|
| Enclosure type | **Sealed** (no bass-reflex port) | Empirically sounded best in testing; gentler impulse response is friendlier to AEC; eliminates port chuffing and tuning complexity. |
| Speaker mounting | **Inner sealed sub-enclosure**, soft-mounted to outer shell | Isolates back-wave, controls cone excursion (the source of non-linearity that breaks AEC at high volume). |
| Disk role | Mass + mic/Pi platform + heatsink | Steel disk floats on soft TPU pads above the speaker sub-enclosure; Pi and mics hard-mounted to disk. |
| Mic mounting | Hard mount to disk via TPU acoustic tunnels | Disk is acoustically quiet (isolated from speaker), so hard mounting is fine and gives best capsule stability. |
| Pi mounting | Hard mount to disk (with thermal pad) | Disk doubles as a heatsink; no compliant layer between Pi SoC and disk. |

## Mechanical Build

### Outer Shell (PLA)

The shell has two halves: a **bottom bowl** containing the speaker subsystem, and a **top cover** (upper hemisphere) over the Pi/mic subsystem. The two halves meet at the steel disk's plane.

**External dia: 82.8 mm; internal dia: 76.8 mm; wall thickness: 3 mm.**

| Part | Wall thickness | Perimeters | Infill | Top/Bottom layers |
|---|---|---|---|---|
| Bottom bowl | 3.0 mm | 4 | 30–40 % gyroid | 5–6 |
| Top cover (upper hemisphere) | 2.4 mm | 4 | 20–25 % gyroid | 4–5 |
| Sealed speaker sub-enclosure | 2.4–3.0 mm | 4 | 30–40 % gyroid | 5 |

**PLA print parameters (apply to all PLA parts):**

- Layer height: **0.2 mm**
- Print temperature: at the **higher end of filament's range** (~215 °C for typical PLA) — improves layer adhesion and reduces ringing.
- Print speed: **≤ 60 mm/s for perimeters**, ≤ 80 mm/s for infill.
- Cooling fan: **30–50 %**, not 100 % — preserves layer welding.
- Infill pattern: **gyroid** (isotropic, self-bracing). Avoid rectilinear/grid.
- Infill/perimeter overlap: **25–30 %** (default 15 % can buzz).

**Heat note:** PLA softens around 60 °C and creeps under load above ~45 °C. If the device runs continuously and the Pi warms the interior, consider **PETG** instead (acoustically similar, heat-tolerant to ~75 °C, prints with the same wall/infill spec).

### Inner Sealed Speaker Sub-Enclosure

Houses the 40 mm 3W driver. Fully airtight — this is what loads the driver against an air spring (controls excursion at high volume → keeps the echo path linear → AEC stays effective).

- Walls 2.4–3.0 mm, 4 perimeters, 30–40 % gyroid infill.
- **0.8 mm TPU gasket between driver flange and enclosure** for an airtight, vibration-decoupled mount.
- **Internal damping:** small amount of polyester fill (~30 % of internal volume) plus optional butyl rubber sheet patches bonded to interior walls. Damps standing waves and absorbs back-wave energy.
- **Seal all wire pass-throughs** with silicone or hot glue.
- The enclosure is then **rigidly part of the bottom bowl** (or bonded to it with T-7000) — it doesn't need to be isolated from the bowl, because the *disk* will be isolated from the bowl/sub-enclosure system.

### Steel Divider Disk (4 mm Stainless Steel)

The disk separates the audio chamber from the Pi/mic chamber. It rides on 4 TPU pads above the sealed speaker sub-enclosure, supports the Pi and HAT (hard-mounted, for heatsinking), supports the mic tunnels, and the top hemisphere clips onto it via magnets.

- Diameter sized to clear the inner sphere wall with ~1 mm radial gap (compliant T-7000 bond fills this; the steel does not rigidly contact the outer shell).
- Bonded to bottom shell using **T-7000** (flexible adhesive that retains compliance after curing).

### Soft-Mount System (Critical)

The disk floats on **4 printed TPU pads** between the top of the speaker sub-enclosure and the underside of the disk.

**Pad specification:**

- **Material:** TPU 85A (or softer if available).
- **Quantity:** 4, placed near the disk rim, widely spaced (maximum rocking resistance).
- **Height:** **3 mm** (2 mm protruding above pocket).
- **Diameter:** ~8 mm round.
- **Infill:** **8–10 % gyroid**, 2 perimeters max, 1–2 top/bottom layers (don't cap with thick solid — the cap dominates stiffness).
- **Bond:** **T-7000** bead on both faces. Cure overnight under full assembly load before any further work.

**Pocket geometry in the speaker sub-enclosure top face:**

- **Pocket depth: 1 mm** (locates pad, doesn't bury it).
- **Pocket diameter: ~11 mm** (3 mm clearance around pad — *essential* for the pad to bulge laterally when compressed; a tight pocket makes the pad hydraulically rigid).
- **Pocket floors coplanar within 0.1 mm** — verify after printing with a straight edge.

**Target acoustic behavior:**

- Suspended mass m = disk + Pi + HAT + reflector + top hemisphere + connectors. Weigh this.
- Resonant frequency f₀ ≈ **60–80 Hz** (well below the speaker's useful output band; isolation improves at 12 dB/octave above ~1.4 × f₀).
- Verify under load: ~10–20 % static compression of the protruding pad height (0.2–0.4 mm of visible sag). More than ~25 % compression is too soft; no visible compression is too stiff.

### Disk-to-Enclosure Clearance

**Resting gap at the closest point: target ~1.5 mm minimum; visible aesthetic rim gap 2.0–2.4 mm.**

The closest-approach point may not be the visible rim — check for any feature protruding upward from the speaker sub-enclosure toward the disk (magnet boss, terminal, screw head). That's where you need the 1.5 mm minimum; the visible rim can be larger.

Measure the gap **after full T-7000 cure and under full load** — it will be smaller than the CAD design due to pad compression.

### Microphone Mounting

The two MEMS mics on the ReSpeaker 2-Mic HAT are angled **40° back of vertical**, pointing up-and-back toward the user.

**TPU acoustic tunnels:**

- **Material:** TPU 85A.
- **Length:** 6–7 mm.
- **Wall thickness:** 1.4–1.6 mm (leave as-is; thicker walls add mass and stiffness, hurting decoupling).
- **Inside diameter:** keep at 3–4 mm or larger to avoid viscous high-frequency losses.
- **Glued to the top hemisphere shell**, touching the mic capsules below.
- **0.6 mm TPU layer between tunnel and top hemisphere mounting point** — creates an impedance mismatch that reflects structure-borne vibration.

**ReSpeaker HAT mounting to disk:**

- **2 mm TPU feet between PCB and disk** at each mounting hole.
- **Nylon screws** (not metal) through the PCB, or metal screws with TPU washers under the heads and between PCB and standoff.
- Any metal-to-metal screw path is a vibration bridge. Eliminate it.

**Pi mounting to disk (for heatsinking):**

- **Hard mount with thermal pad or paste** between SoC and disk. **No TPU between Pi SoC and disk** — TPU is a thermal insulator and would defeat the heatsink function.
- The Pi has no moving parts and does not vibrate; hard mounting is correct here because the *disk itself* is isolated from the speaker's vibration via the soft mount below it.
- Monitor SoC temperature with `vcgencmd measure_temp` under sustained load to confirm thermal margin.

### Top Hemisphere

- Mounted to the steel disk via **magnets** (already designed).
- **0.6 mm TPU pads between each magnet and the disk** to break the structure-borne path.
- Has a 50 mm hole for the inner semi-transparent light dome.
- Light dome is mounted on the PCB structure (not the top hemisphere shell) and uses a 2 mm gap to the hemisphere — this gap is the upper chamber's natural ventilation path.

### Wire Routing (Critical Bypass Path Control)

The whole isolation scheme assumes the 4 TPU pads are the **only mechanical path** from the speaker enclosure to the disk. Wires can defeat this.

- Use **thin, flexible wire** (silicone-jacketed AWG 28–30 or finer) for speaker leads crossing the boundary.
- **Service loop:** leave several mm of slack so the wire can flex without transmitting force.
- Avoid stiff jackets, sleeving, or strain reliefs that create rigid bridges.
- Seal all wire pass-throughs in the sealed speaker box with silicone or hot glue — leaks act as accidental ports.

## Internal Damping (Optional but Worthwhile)

- **Butyl rubber sheet patches** (automotive sound deadener — "Dynamat" type) on the **inside of the bottom bowl walls**. Covers maybe 30–40 % of the inner surface. Converts panel vibration to heat with very high efficiency — far better than thicker plastic walls.
- **Light polyester fill (~30 %)** inside the sealed speaker sub-enclosure. Damps internal standing waves.
- **Do NOT** bridge the isolation gap between speaker sub-enclosure and disk with any material — any contact across that gap reinstates a vibration path and defeats the soft mount.

## Software Configuration (PipeWire + AEC)

### Hardware Stack

- **ReSpeaker 2-Mic HAT** based on TLV320AIC3204 codec.
- Single I²S clock domain: playback and capture are clock-synchronous (ideal for AEC).
- Native rate: **48 kHz**.
- ALSA device: typically appears as `seeed2micvoicec`.

### AEC Configuration

`~/.config/pipewire/pipewire.conf.d/99-echo-cancel.conf`:

```
context.modules = [
  {
    name = libpipewire-module-echo-cancel
    args = {
      library.name = "aec/libspa-aec-webrtc"
      audio.rate = 48000
      audio.channels = 1
      audio.position = [ MONO ]
      webrtc.high_pass_filter = true
      webrtc.noise_suppression = true
      webrtc.voice_detection = false
      webrtc.gain_control = false
      webrtc.extended_filter = false
      capture.props = {
        node.name = "aec_capture"
        target.object = "alsa:acp:seeed2micvoicec:2:capture"
        audio.channels = 2
        audio.position = [ FL FR ]
        node.force-rate = 48000
        node.force-quantum = 480
      }
      source.props = {
        node.name = "aec_input"
        node.description = "Echo-Cancelled Mono Mic"
        media.class = "Audio/Source"
        audio.channels = 1
        audio.position = [ MONO ]
        priority.driver = 1500
        priority.session = 1500
      }
      sink.props = {
        node.name = "aec_output"
        node.description = "Echo-Cancel Mono Reference"
        media.class = "Audio/Sink"
        audio.channels = 1
        audio.position = [ MONO ]
        priority.driver = 1500
        priority.session = 1500
      }
      playback.props = {
        node.name = "aec_playback"
        target.object = "alsa_output.platform-soc_sound.stereo-fallback"
        audio.channels = 1
        audio.position = [ MONO ]
        node.force-rate = 48000
        node.force-quantum = 480
      }
    }
  }
]
```

**Important:** the hardware mic capture stays **stereo** (2 channels) — the ReSpeaker HAT has two physical mics and ALSA exposes them as a stereo source; AEC reads stereo and downmixes internally to mono. Everything else in the chain is mono.

### Playback Limiter (Driver Protection + AEC Quality at High Volume)

`~/.config/pipewire/pipewire.conf.d/10-speaker-limiter.conf`:

```
context.modules = [
  { name = libpipewire-module-filter-chain
    args = {
      node.description = "Speaker Limiter"
      media.name       = "Speaker Limiter"
      filter.graph = {
        nodes = [
          {
            type  = builtin
            name  = limiter
            label = max_ge
            control = {
              "Max" = 0.5
            }
          }
        ]
      }
      capture.props = {
        node.name      = "limiter_input"
        media.class    = Audio/Sink
        audio.channels = 1
        audio.position = [ MONO ]
      }
      playback.props = {
        node.name      = "limiter_output"
        node.passive   = true
        audio.channels = 1
        audio.position = [ MONO ]
        target.object  = "aec_output"
      }
    }
  }
]
```

This uses **PipeWire's built-in `max_ge` limiter** — no external packages needed. `Max` is the linear amplitude ceiling:

| `Max` value | Ceiling | Loudness loss vs. unity |
|---|---|---|
| 1.0 | 0 dBFS (off) | none |
| 0.707 | −3 dB | ~3 dB |
| 0.5 | −6 dB | ~6 dB |
| 0.354 | −9 dB | ~9 dB |
| 0.25 | −12 dB | ~12 dB |

**Tuning procedure:**

1. Start at `"Max" = 0.5` (−6 dB).
2. Play test audio at full source volume.
3. If clean → raise toward `0.7` or `0.8`.
4. If distorted → lower to `0.354` or `0.25`.
5. Find the highest ceiling that keeps AEC working at full volume.

Each edit requires `systemctl --user restart pipewire pipewire-pulse wireplumber`.

### Optional: High-Pass Filter Before Limiter

If the limiter alone isn't enough at high volume, add a high-pass filter ahead of it. Modify the `filter.graph` block:

```
filter.graph = {
  nodes = [
    {
      type   = builtin
      name   = hpf
      label  = bq_highpass
      control = { Freq = 150.0  Q = 0.707 }
    }
    {
      type  = builtin
      name  = limiter
      label = max_ge
      control = { "Max" = 0.5 }
    }
  ]
  links = [
    { output = "hpf:Out"  input = "limiter:In" }
  ]
}
```

A 150 Hz second-order Butterworth HPF removes deep bass that the small driver can't reproduce cleanly anyway and dramatically reduces cone excursion. For voice/notification use this is inaudible except as cleaner output at high volume.

### Routing

The default playback sink should be `limiter_input` (apps → limiter → AEC → speaker). The default recording source should be `aec_input` (cleaned mic).

```bash
wpctl status   # find node IDs
wpctl set-default <limiter_input_ID>
wpctl set-default <aec_input_ID>
```

Defaults persist in `~/.local/state/wireplumber/default-nodes`.

### Verifying the Routing

```bash
pw-link --links | grep -E 'limiter|aec|alsa'
```

The expected chain:

```
limiter_output → aec_output (AEC sink)
aec_playback → alsa_output (HAT speaker)
alsa_input (HAT mic) → aec_capture
```

`pw-top` shows live sample rates; verify all nodes run at 48 000 Hz with no resampling between stages.

## Testing & Validation

### Acoustic / Build Verification

1. **Pressure-leak test:** seal the speaker hole with your hand, press gently on the speaker sub-enclosure. Pressure should release slowly. Quick release = leak.
2. **Tap test:** with everything assembled, tap the bottom bowl. The disk/Pi/mic assembly above should feel *noticeably deader* than the bowl — confirms isolation is working.
3. **Pink noise sweep:** `play -n -c 1 synth 30 pinknoise` (requires `sox`). Listen around the enclosure for buzzes, leaks, and rattles — pink noise reveals problems music masks.

### AEC Performance Verification

```bash
# Terminal 1 — play continuous tone through the full chain:
play -n synth 30 sine 1000

# Terminal 2 — record AEC output:
pw-record --target=aec_input aec_test.wav
# wait ~10 seconds, Ctrl+C, then:
pw-play aec_test.wav
```

The 1 kHz tone should be heavily attenuated in the recording. Repeat at progressively higher volumes; the level at which residual playback becomes audible defines your current AEC headroom.

### Thermal Verification

```bash
# Under sustained CPU load (e.g., audio processing):
watch -n 2 vcgencmd measure_temp
```

Pi Zero 2W should stabilize below ~70 °C under load. If it climbs higher, the disk's heatsinking isn't carrying enough heat — check thermal pad contact pressure and consider adding a small thermal gap-pad path from disk to the bottom shell.

## Vibration Bypass Paths — Pre-Build Checklist

The 4-TPU-pad soft mount only works if it's the **only** path from speaker to disk. Verify before final assembly:

- [ ] Disk rim is **not** rigidly bonded to the outer shell (use T-7000's compliance, not rigid epoxy).
- [ ] No metal-to-metal screws connect any rigid component on the disk-side to any rigid component on the speaker-side.
- [ ] Wires crossing the boundary are thin, slack, and have service loops.
- [ ] No felt, foam, or any material **bridges the gap** between the speaker sub-enclosure and the disk underside. Air gap only.
- [ ] All 4 pad seats are coplanar (within 0.1 mm).
- [ ] T-7000 has cured under load for at least 12 hours before measurement.

## Materials Summary

| Material | Used for | Why |
|---|---|---|
| PLA (or PETG if hot) | All rigid shell parts | Stiff, easy to print, sufficient mass at 3 mm walls and 30–40 % infill. |
| TPU 85A | Soft mount pads, mic tunnels, PCB feet, magnet pads, driver gasket | Compliant, lossy, printable, tuneable via infill %. |
| Stainless steel disk, 4 mm | Mid-divider | Mass loading, mic platform, Pi heatsink, acoustic separation. |
| T-7000 adhesive | Disk-to-shell, pads-to-enclosure, general flexible bonds | Stays flexible after cure; airtight; doesn't short out compliance. |
| Butyl rubber sheet (optional) | Interior lining of bottom bowl | Highly lossy panel damping. |
| Polyester fill (small amount) | Interior of sealed speaker box | Damps internal standing waves. |
| Thermal pad/paste | Pi SoC ↔ disk interface | Heat transfer; the only place hard contact is wanted. |

## Why This Design (Key Decisions Recap)

**Why sealed instead of bass-reflex?** Empirically sounded best in testing. With Vb ≈ 90 cm³ behind a 40 mm driver whose Vas is larger, the system is compliance-limited regardless of porting. Sealed has gentler impulse response, no port ringing, no port chuffing at high level — all of which makes AEC's job easier.

**Why a sealed speaker sub-enclosure instead of just sealing the bottom shell?** A separate sub-enclosure provides a controlled air-spring load on the driver, limiting cone excursion at low frequencies (where excursion is highest). Excursion past the linear range is the main mechanism by which AEC fails at higher volume. This is the same trick the Echo Dot uses.

**Why hard-mount the Pi if everything else is decoupled?** The Pi has no moving parts and produces essentially no vibration. Hard mounting gives best thermal contact for heatsinking through the disk, and doesn't compromise anything — because the *disk* is the thing being isolated, not the Pi.

**Why is the steel disk both the heatsink and the mic platform?** Because once it's isolated from the speaker via the 4 TPU pads, it's a quiet rigid mass — ideal for mics (no vibration) and for heatsinking (large area, high conductivity). Wearing both hats.

**Why printed TPU pads instead of nano tape or foam?** Tuneable via infill %, doesn't creep significantly under load like nano tape, doesn't compression-set like foam/felt, prints cleanly, bonds with T-7000. Permanent rather than prototype.

**Why 4 pads, not 3 or 6?** 3 is the minimum for a defined plane but vulnerable to tilt/seesaw under uneven loading. 4 is stable against tilt with widely spaced anchoring. More than 4 increases total stiffness (parallel springs), raising f₀ and *reducing* isolation — no benefit.

**Why no felt bridging the gap?** Any material touching both sides of the isolation gap acts as a parallel mechanical spring (k_total = k_pads + k_felt), raising f₀ and reducing isolation. The empty air gap is doing essential work. Felt belongs *inside* chambers or lining one surface only — never across the isolation boundary.