# SimonK (tgy.asm) throttle calibration internals

Method note: the primary source is the current `master` of github.com/sim-/tgy (last commit 2017-01-13), downloaded raw with curl and read directly (`tgy.asm`, `README.md`, `Makefile`, `bs.inc`, `bs_nfet.inc`, `afro*.inc`). Line numbers below refer to `tgy.asm` on master (T = https://github.com/sim-/tgy/blob/master/tgy.asm, R = https://github.com/sim-/tgy/blob/master/README.md). Web searches and fetches used the TinyFish CLI only. Beep durations and frequencies, and the arming-delay estimates, are my own calculations from the code and are labelled as inferences. Cheap "SimonK 30A" ESCs often run older or vendor-modified builds, so the behaviour described here is that of the upstream firmware.

## 1. What triggers calibration mode, and is it enabled in common builds?

### Takeaway
Calibration starts whenever the ESC is **disarmed** (not only right after power-up) and receives a stable PWM pulse at or above `PROGRAM_RC_PULS`. That threshold is midway between STOP and FULL, which is **1460 µs** by default. `RC_CALIBRATION = 1` is a hard-coded `.equ` in tgy.asm that no board `.inc` file overrides, so every upstream hex has calibration enabled (bs.hex, bs_nfet.hex, afro*.hex, tgy.hex and the rest). The only lockout is a brown-out reset.

### Cited Findings
- `.equ RC_CALIBRATION = 1 ; Support run-time calibration of min/max pulse lengths` is set unconditionally in tgy.asm (line 189). None of the board include files (bs.inc, bs_nfet.inc, afro.inc, afro_nfet.inc) define it. — [tgy.asm L189](https://github.com/sim-/tgy/blob/master/tgy.asm#L189)
- `PROGRAM_RC_PULS = (STOP_RC_PULS + FULL_RC_PULS) / 2 ; Normally 1460`. With RC-car reverse mode (`RC_PULS_REVERSE`, default 0) it is instead `(STOP + FULL*3)/4`, which is 1660. — [tgy.asm L219-225](https://github.com/sim-/tgy/blob/master/tgy.asm#L219)
- README: "The only requirement is that the input pulse has to be at or above PROGRAM_RC_PULS (default 1460us) to enter programming mode. This will differ slightly on boards with no external oscillator." — [README](https://github.com/sim-/tgy/blob/master/README.md#throttle-calibration-and-programming)
- How it works in the code: in the disarmed loop (`i_rc_puls2`/`i_rc_puls_rx`, L3439-3463), every received pulse calls `evaluate_rc_init` (L2386). If the `NO_CALIBRATION` flag is clear, that routine jumps to `rc_prog1`. There it tests the pulse against `PROGRAM_RC_PULS`. At or above the threshold, it starts measuring the high pulse. Below it, it falls through to normal `evaluate_rc_puls`. — [tgy.asm L2399-2417](https://github.com/sim-/tgy/blob/master/tgy.asm#L2399)
- `NO_CALIBRATION` is set only when the reset cause is a brown-out (the startup beeps are then f3 f1, "dead cellphone"). README: "As of 2012-03-15, throttle calibration is disabled when a brown-out reset is detected," because sim- once accidentally calibrated an ESC when a weak NiCd pack browned out the ESCs. — [tgy.asm L3321-3326](https://github.com/sim-/tgy/blob/master/tgy.asm#L3321); [README](https://github.com/sim-/tgy/blob/master/README.md#throttle-calibration-and-programming)
- The feature has existed "Since the 2012-01-04 release." — [README](https://github.com/sim-/tgy/blob/master/README.md#throttle-calibration-and-programming)
- The Makefile `ALL_TARGETS` list includes bs.hex, bs_nfet.hex, afro.hex, afro_nfet.hex, tgy.hex, kda.hex, tp.hex and others, all built from the same tgy.asm. — [Makefile](https://github.com/sim-/tgy/blob/master/Makefile)
- bs.inc and bs_nfet.inc set `F_CPU = 16000000` and `USE_INT0 = 1`, so the PWM input is on INT0. They contain no calibration-related overrides. — [bs_nfet.inc](https://github.com/sim-/tgy/blob/master/bs_nfet.inc)
- Community reports pair HobbyKing F-30A and Blue Series 30A ESCs with bs_nfet.hex. For example, "Die 30A und die 12A Version der Blue Series laufen beide mit der bs_nfet.hex Firmware" — [rc-sub.de](https://www.rc-sub.de/diverse-elektronik/67-umflashen-von-brushless-reglern); "F30a HK ... SimonK BS-Nfet.hex Version von 2013-09-20" — [fpv-community.de](https://fpv-community.de/threads/ntm-propdrive-2826-und-simonk.36892/). One RCGroups poster notes that tgy.hex and bs_nfet.hex do *not* work on RCTimer 30A NFS boards, which need custom builds — [RCGroups flashing thread p664](https://www.rcgroups.com/forums/showthread.php?1513678-RCTimer-Turnigy-Hobbywing-ESC-DIY-Firmware-Flashing/page664).

### Inferences
- "Power up at full throttle" is the documented procedure, but it is not strictly required. Because `evaluate_rc_init` runs on every pulse while disarmed, raising the stick above about 1460 µs at any time before the ESC arms also enters calibration. So does raising it after a signal-loss disarm (`control_disarm` returns to the same loop).
- Any stick position at or above about 1460 µs counts. You do not need exactly 100%. The *value stored* as "high" is whatever stable pulse is being received (see section 2), so calibrating at half-stick would make half-stick the new full throttle.

### Gaps
- I could not tell which firmware build (or which vintage) ships on unbranded "SimonK 30A" ESCs. Some may run vendor-modified or pre-2012 code that lacks calibration or the brown-out lockout. Verify on the actual unit.

## 2. Full-throttle hold time, beeps when max/min are stored, and the "repeating tune"

### Takeaway
The high pulse is stored after **31 consecutive pulses** that all stay within **±10 µs** of the first pulse. That takes about 0.62 s at 50 Hz, after the power-up beeps. The ESC then plays **one f3 beep**. It then waits **silently** while the stick stays high. When the stick drops below the stored high value, it averages **34 stable pulses**, plays **two f3 beeps**, writes EEPROM and returns to the arming loop. The upstream source has no repeating tune during calibration.

### Cited Findings
- High-pulse averaging count: `ldi temp2, 32 * 31/32 ; Full speed pulse averaging count (slightly below exact)`, which is 31 pulses. Low pulse: `32 * 17/16 ; Stop/reverse pulse (slightly above exact)`, which is 34 pulses. The 32-loop scale factor (×8 then the top 16 bits) means these counts also bias the stored average. — [tgy.asm L2412, L2422](https://github.com/sim-/tgy/blob/master/tgy.asm#L2405)
- Drift check: `.equ MAX_DRIFT_PULS = 10 ; Maximum jitter/drift microseconds during programming`. If any pulse differs from the first by more than this, the code goes to `rc_prog0` ("Wait for stick movement to settle", `wait240ms`) and starts over. — [tgy.asm L232](https://github.com/sim-/tgy/blob/master/tgy.asm#L232), [L2404-2449](https://github.com/sim-/tgy/blob/master/tgy.asm#L2404)
- Beep sequence in the code: after the high value is stored, `; One beep: high (full speed) pulse received` → `rcall beep_f3`. After the low value is stored, the same `beep_f3` is followed by `wait30ms` and a second `beep_f3`, commented `; Two beeps: low (stop/reverse) pulse received`. In reverse mode only, a neutral pulse is learned next and a third beep follows. Then `rc_prog_done: rcall eeprom_write_block` and `rjmp puls_scale`. — [tgy.asm L2457-2474](https://github.com/sim-/tgy/blob/master/tgy.asm#L2457)
- After the high value is stored, the code loops to `rc_prog1`. `rc_prog3` then says "If not learning the high pulse, we should stay below it … Restart while pulse not lower than learned high pulse." So while the stick stays high, the ESC just keeps re-reading pulses with no beeps and no timeout. — [tgy.asm L2418-2421](https://github.com/sim-/tgy/blob/master/tgy.asm#L2418)
- README procedure: "set to full throttle, power up the ESC and wait for a single beep after the typical rising initialization beeps … Move the stick or knob to the lowest setting, and wait for two beeps … If the stick is not moved after the final setting, the ESC should now write the RAM settings to EEPROM, and continue startup." — [README](https://github.com/sim-/tgy/blob/master/README.md#throttle-calibration-and-programming)
- User reports match this: a "Short tune ending in a beep, throttle down and then two short beeps followed by a long one" — [RCGroups thread 1961877 (pug398, 2013)](https://www.rcgroups.com/forums/showthread.php?1961877-SimonK-ESC-no-long-beep-when-calibrating). The "long one" is the arming signal (section 4).
- Beep tones: `beep_f1` = 80 cycles with a 200-count off period, `beep_f2` = 100/180, `beep_f3` = 120/160, `beep_f4` = 140/140. Each beep uses a different pair of FETs, so a dead FET shows up as a missing beep. — [tgy.asm L1768-1835](https://github.com/sim-/tgy/blob/master/tgy.asm#L1768); README: "4 main beep frequencies … f1 through f4, where a higher number indicates a higher frequency. Repetition indicates longer beeps." — [README Troubleshooting](https://github.com/sim-/tgy/blob/master/README.md#troubleshooting)

### Inferences
- **Approximate beep acoustics (my calculation; label as estimate).** Timer0 is clk/8, so 2 MHz on a 16 MHz build. Each cycle is about 16 µs on, then 16 × off-count × 0.5 µs off. That gives roughly: f1 ≈ 620 Hz × ~130 ms, f2 ≈ 690 Hz × ~145 ms, f3 ≈ 770 Hz × ~155 ms, f4 ≈ 880 Hz × ~160 ms.
- **Minimum hold time at full throttle.** The power-up beeps (f1 f2 f3) take about 0.45 s, plus about 30 ms of settling. Then come 1 + 31 pulses with no drift greater than 10 µs: about 0.64 s at 50 Hz, about 0.08 s at 400 Hz. Holding full throttle for 1-2 s after power is applied is comfortably enough. A noisy or drifting signal (more than 10 µs jitter) restarts the measurement every 240 ms and can hold off the beep indefinitely.
- **Stored values are deliberately biased.** The stored high value is about 31/32 of the measured average (for example, measured 1900 µs → stored about 1841 µs), so full throttle is reached slightly before full stick. The stored low value is about 17/16 of the average (for example, measured 1000 µs → stored about 1062 µs), so the real stick-low position sits safely below "stop". README: "margins of 1/16th on the low end and 1/32nd on the high end are used to try to avoid problems with arming and reaching full throttle during temperature extremes." — [README](https://github.com/sim-/tgy/blob/master/README.md#throttle-calibration-and-programming)
- **"Repeating tune at full throttle."** Nothing in upstream tgy.asm plays a repeating tune while full throttle is held in calibration: after the single f3 beep it waits silently. The repeating patterns in the source are listed below. If an ESC sold as "SimonK" keeps repeating a melody at full throttle, that suggests non-SimonK (stock or BLHeli-style) firmware, or a modified build. Treat that as a hypothesis, not a confirmed fact.
  - Watchdog-reset siren f1 f1 f3 f3, looped forever.
  - Unknown-reset bit beeps, looped.
  - No-signal beacon (f3 every 4-8 s).
  - Start-failed beacon (f4 every about 0.5 s).
  - Optional rapid f4 RCP-error beeps (disabled by default).

### Gaps
- I did not find a post by sim- describing a "repeating tune at full throttle". The claim that this indicates non-SimonK firmware is an inference from the absence of any such code path.

## 3. Default pulse values, accepted range, frame rate

### Takeaway
The defaults are STOP 1060 µs, FULL 1860 µs, MAX 2400 µs and MIN 768 µs. Pulses shorter than 768 µs are re-interpreted as OneShot125 (1/8 scale) if they fall in the scaled range, and otherwise discarded. The firmware measures each pulse width with timer1 and has **no 50 Hz requirement**: any refresh rate works, provided pulses keep arriving often enough (within about 131 ms while running).

### Cited Findings
- Defaults: `STOP_RC_PULS = 1060 ; Stop motor at or below this pulse length`, `FULL_RC_PULS = 1860 ; Full speed at or above`, `MAX_RC_PULS = 2400 ; Throw away any pulses longer than this`, `MIN_RC_PULS = 768 ; Throw away any pulses shorter than this`, `MID_RC_PULS = (STOP+FULL)/2`. Comment: "These are now defaults which can be adjusted via throttle calibration (stick high, stick low, (stick neutral) at start)." — [tgy.asm L208-215](https://github.com/sim-/tgy/blob/master/tgy.asm#L208)
- `RCP_ALIAS_SHIFT = 3 ; Enable 1/8th PWM input alias ("oneshot125")`. A pulse below `MIN_RC_PULS` is accepted if it lies between MIN/8 (96 µs) and MAX/8 (300 µs), and the ESC toggles into alias mode and rescales. Calibration pulses are shifted ×8 in `rc_prog_get_rx`. — [tgy.asm L216, L2389-2397, L2476-2487, L2553-2562](https://github.com/sim-/tgy/blob/master/tgy.asm#L2389)
- Long pulses: the rising edge arms OCR1B at rise + `MAX_RC_PULS`. If the pulse is still high when that fires, the falling edge is flagged `RCP_ERROR` and the pulse is ignored. — [tgy.asm L1587-1622](https://github.com/sim-/tgy/blob/master/tgy.asm#L1587)
- Defaults are written into the EEPROM image and used until something is saved: `eeprom_defaults_w: … FULL_RC_PULS*CPU_MHZ, STOP_RC_PULS*CPU_MHZ, MID_RC_PULS*CPU_MHZ`. — [tgy.asm L472-476](https://github.com/sim-/tgy/blob/master/tgy.asm#L472); README: "The default range is set at the top of tgy.asm (stop at 1060us, full throttle at 1860us) and is not changed if no new value is saved to the EEPROM." — [README](https://github.com/sim-/tgy/blob/master/README.md#throttle-calibration-and-programming)
- Signal timeouts: `RCP_TOT = 2 ; Number of 65536us periods before considering rc pulse lost`, used as the running timeout. Timer1 overflows every 4096 µs, and `rc_timeout` is decremented every 16 overflows (about 65.5 ms). — [tgy.asm L206, L1540-1563, L2589-2591](https://github.com/sim-/tgy/blob/master/tgy.asm#L1540)
- README recommends that, with a flight controller, you can simply match the ESC defaults instead of calibrating: `set minthrottle=1064`, `set maxthrottle=1864` (baseflight). — [README](https://github.com/sim-/tgy/blob/master/README.md#throttle-calibration-and-programming)
- Internal-oscillator boards (tgy.hex-type) "may be off by 5% - 10% between each board, and will also drift by 10% or more over a 40 degree Celsius temperature range", which is why calibration is recommended. Boards with an external resonator can use the defaults. — [README](https://github.com/sim-/tgy/blob/master/README.md#throttle-calibration-and-programming)
- Scaling accepts any calibrated span, mapped in 16.16 fixed point. Spans of roughly 50 µs or less at 16 MHz fail (the multiplier saturates). — [tgy.asm `puls_find_multiplicand` comments L2737-2745](https://github.com/sim-/tgy/blob/master/tgy.asm#L2737)

### Inferences
- 50 Hz, 400 Hz and OneShot125 inputs are all accepted, as long as the pulse width (not the frame rate) is in range. At 50 Hz the 131 ms running timeout tolerates about 6 missing frames.
- **Effective motor-start threshold.** Duty is non-zero for any pulse at or above the stored low value (`sub neutral; brcc puls_plus`, with `MIN_DUTY` added in `rc_do_scale`). A calibrated ESC therefore starts the motor at about measured-min × 17/16, roughly 60-65 µs above the transmitter's minimum. An uncalibrated ESC starts at about 1060 µs. — [tgy.asm L2526-2530, L2581-2583](https://github.com/sim-/tgy/blob/master/tgy.asm#L2526)

### Gaps
- I found no explicit upper refresh-rate limit in the code beyond the requirement that edges are cleanly separated (a pulse must fall before the next one rises). I did not test this.

## 4. After min is stored: immediate arm or power cycle? Cell-count beeps?

### Takeaway
No power cycle is needed. After the second f3 beep the values go to EEPROM and the throttle scaling is recomputed. The ESC returns to the disarmed loop and arms as soon as it sees about 10 valid zero-throttle pulses, signalled by **f4 f4 f4** played back-to-back, which sounds like one long beep. Upstream release builds do **not** beep the cell count: `BLIP_CELL_COUNT = 0` is hard-coded.

### Cited Findings
- `rc_prog_done: rcall eeprom_write_block; rjmp puls_scale ; Calculate the new scaling factors`. This returns to the caller in the disarmed loop. — [tgy.asm L2473-2474](https://github.com/sim-/tgy/blob/master/tgy.asm#L2473)
- Arming logic: `rc_no_set_duty: ldi temp1, 12 ; More than 10 needed to arm` increments `rc_timeout` per zero-duty pulse. `i_rc_puls_rx` requires `rc_duty == 0` and `rc_timeout >= 10`. Any non-zero duty jumps to `i_rc_puls1`, which clears the counter. On success it plays `beep_f4 ×3 ; signal: rcpuls ready`. — [tgy.asm L2592-2596](https://github.com/sim-/tgy/blob/master/tgy.asm#L2592), [L3456-3482](https://github.com/sim-/tgy/blob/master/tgy.asm#L3456)
- README: "Once a valid input source is found and receiving idle throttle, f4 f4 f4 (a long f4 beep) indicates that the ESC is armed"; "The ESC should recognize the same pulse length input as a valid arming pulse, and arm and work as usual." — [README](https://github.com/sim-/tgy/blob/master/README.md#troubleshooting)
- Cell count: `.equ BLIP_CELL_COUNT = 0 ; Blip out cell count before arming`, along with `CELL_COUNT = 0` (auto). The blip code exists, but it only runs if someone rebuilds with `BLIP_CELL_COUNT = 1`. — [tgy.asm L199-200, L3361-3384](https://github.com/sim-/tgy/blob/master/tgy.asm#L199)
- A user's account of a HobbyKing 30A SimonK ESC: "set to full throttle, powered up … heard ONE beep, moved the throttle back down … TWO beeps, then ONE LONG beep." — [RCGroups 1961877](https://www.rcgroups.com/forums/showthread.php?1961877-SimonK-ESC-no-long-beep-when-calibrating)

### Inferences
- Arming delay (my estimate): each zero pulse adds 1 to the counter, and 1 is subtracted every 65.5 ms. Arming therefore takes about 0.3 s at 50 Hz and is almost instant at 400 Hz.
- A full successful calibration therefore sounds like: f1 f2 f3 (rising startup), then one f3, then (stick low) two f3, then one long f4 (armed). If the 2-beep step happens but the long beep never comes, the stick-low pulse is not reading as zero, for example because it drifted or is noisy.
- Short "per-cell" beeps heard on some cheap "SimonK 30A" ESCs would indicate a custom build with `BLIP_CELL_COUNT` enabled, or non-SimonK firmware. Upstream hexes emit no cell beeps.

### Gaps
- None in the source. The behaviour of vendor-modified builds is unknown.

## 5. Power-up with non-zero throttle (no calibration), and the beep meanings for "no signal", "armed" and "throttle not at zero"

### Takeaway
- Throttle above zero but below about 1460 µs: the ESC **stays silent and disarmed** until throttle reaches zero. There is no specific "throttle not at zero" beep.
- No signal at all: an f3 beacon after about 8 s, then every about 4 s.
- Signal lost while armed: f3 f2, then the ESC disarms.
- Armed: f4 f4 f4, played back-to-back so it sounds like one long f4.

### Cited Findings
- Non-zero throttle while disarmed: `adiw YL,0 ; Test for zero` → `brne i_rc_puls1`, which clears `rc_timeout` and `rct_beacon`. Arming only proceeds after enough consecutive zero-throttle pulses. — [tgy.asm L3435-3463](https://github.com/sim-/tgy/blob/master/tgy.asm#L3435). README: "If you are unable to start the motor and are not hearing the forth, long beep, try lowering the throttle trim, or raise it all the way to start throttle calibration." — [README](https://github.com/sim-/tgy/blob/master/README.md#troubleshooting)
- No signal while disarmed: `cpi temp1, 120 ; Beep every 120 * 16 * 65536us (~8s)`, then `ldi temp1, 60 ; Double rate after the first beep`, then `rcall beep_f3 ; Beacon` (`BEACON = 1` by default). README: "an f3 beep will be emitted after about 8 seconds and then every 4 seconds." — [tgy.asm L191, L3447-3454](https://github.com/sim-/tgy/blob/master/tgy.asm#L3447)
- Signal lost while armed and idle: `cpi temp1, 30 ; Disarm after ~2 seconds of no signal` → `beep_f3`, `beep_f2 ; Play beeps for signal lost, disarming` → `control_disarm`. The README says "about 1 second". The code comment says about 2 s (30 × 65.5 ms ≈ 1.97 s). The two conflict and the code is authoritative. — [tgy.asm L3556-3563](https://github.com/sim-/tgy/blob/master/tgy.asm#L3556); [README](https://github.com/sim-/tgy/blob/master/README.md#troubleshooting)
- Reset-cause beeps (README and code):
  - f1 f2 f3: normal power-on.
  - f3 f1: brown-out; calibration is disabled.
  - f4: external reset (after programming).
  - Looping f1 f1 f3 f3: watchdog reset.
  - Looping 8× f2/f4: an unknown reset cause; the beeps spell out the MCUCSR bits.
  — [tgy.asm L3314-3357](https://github.com/sim-/tgy/blob/master/tgy.asm#L3314); [README](https://github.com/sim-/tgy/blob/master/README.md#troubleshooting)
- "fast repeating beeps of f4 while idle: Noise on PWM input detected". This only applies when `BEEP_RCP_ERROR` is enabled, and it is 0 by default. — [README](https://github.com/sim-/tgy/blob/master/README.md#troubleshooting); [tgy.asm L217, L3210-3221](https://github.com/sim-/tgy/blob/master/tgy.asm#L210)
- Start failure: if the motor cannot be started for a long time, the ESC powers off and plays `beep_f4 ; "Start failed" beacon` every about 0.5 s until throttle returns to zero, then disarms. — [tgy.asm L3842-3854](https://github.com/sim-/tgy/blob/master/tgy.asm#L3842)
- Continuously-high input (a DC level, not PWM) for about 2 s while disarmed jumps to the boot loader if one is present (`BOOT_JUMP = 1`). README: "long periods of high PWM input while disarmed will cause a jump to the boot loader." — [tgy.asm L164, L3160-3172](https://github.com/sim-/tgy/blob/master/tgy.asm#L3160); [README Boot Loader Fuses](https://github.com/sim-/tgy/blob/master/README.md)

### Inferences
- If you power up at, say, 1300 µs (above stop, below the program threshold), you hear only the three startup beeps, then silence. There is no beacon either, because `rct_beacon` is reset on every valid pulse. This is easy to mistake for a dead ESC.
- If you power up at or above 1460 µs while the transmitter is jittery or drifting, the ESC may wait in calibration without beeping. In the boot-loader-jump code, normal PWM pulses keep resetting `rct_boot`, so ordinary full-throttle PWM should *not* trigger the boot-loader jump. Only a stuck-high line does.

### Gaps
- None in the source. Note the README/code discrepancy on signal-loss timing (about 1 s vs about 2 s).

## 6. EEPROM storage and reset

### Takeaway
Yes, calibration is saved to EEPROM. It is an 8-byte block (signature 31337, plus the high, low and neutral pulse values) at EEPROM offset 0x80. There is **no stick or menu reset**. To remove a calibration you erase the EEPROM, or reflash without the EESAVE fuse. In practice, simply recalibrating overwrites it.

### Cited Findings
- EEPROM block layout: `eeprom_sig_l/h`, `puls_high_l/h`, `puls_low_l/h`, `puls_neutral_l/h` ("saved pulse lengths during throttle calibration"). `EEPROM_SIGN = 31337`, `EEPROM_OFFSET = 0x80`. — [tgy.asm L280-281, L401-420](https://github.com/sim-/tgy/blob/master/tgy.asm#L401)
- At boot `eeprom_read_block` and `eeprom_check_reset` run. If the signature does not match, the RAM copy is loaded from `eeprom_defaults_w`, with no write ("to avoid writing to the EEPROM until we actually set something non-default"). — [tgy.asm L1858-1874, L3294-3296](https://github.com/sim-/tgy/blob/master/tgy.asm#L1858)
- `eeprom_write_block` only rewrites bytes that differ. — [tgy.asm L1887-1923](https://github.com/sim-/tgy/blob/master/tgy.asm#L1887)
- README: "There is currently no way to reset (remove) the calibration other than by clearing the EEPROM (or reflashing without EESAVE set). This may be implemented in the future by some basic stick programming feature." Also: "the values may be adjusted in EEPROM directly." — [README](https://github.com/sim-/tgy/blob/master/README.md#throttle-calibration-and-programming)
- Fuses: "the last nibble of the hfuse should be set to 'a' or '2' to also enable EESAVE - save EEPROM on chip erase." — [tgy.asm L67-69](https://github.com/sim-/tgy/blob/master/tgy.asm#L67)
- The MK I2C (BL-Ctrl v2) builds have their own EEPROM reset and write flags set via MKTool. These do not apply to PWM-only bs/bs_nfet boards (`USE_I2C = 0`). — [tgy.asm L1725-1730, L3565-3570](https://github.com/sim-/tgy/blob/master/tgy.asm#L1725)
- SimonK has no other programmable settings: "There are no programming settings with simonk firmware" (user statement, consistent with the source). — [RCGroups 1961877](https://www.rcgroups.com/forums/showthread.php?1961877-SimonK-ESC-no-long-beep-when-calibrating)

### Inferences
- A calibration made while the ESC was cold or hot, or at low voltage, persists across power cycles. On internal-RC-oscillator boards, recalibrate at representative conditions (README: "maintain a close temperature and at least 6-7V input voltage").

### Gaps
- None.

## 7. MOTOR_BRAKE and the startup power settings (PWR_MIN_START and related)

### Takeaway
`MOTOR_BRAKE = 0` and `LOW_BRAKE = 0` are hard-coded in upstream tgy.asm, so release hexes have no brake. `PWR_MIN_START`/`PWR_MAX_START` are **caps** on duty during startup (POWER_RANGE/6, rising to /4). They are not a minimum. They do **not** set the throttle at which the motor begins to start. Any non-zero throttle triggers a start attempt, with duty = min(throttle duty, start cap). The lowest non-zero duty is `MIN_DUTY` (56/856, about 6.5% at 16 MHz).

### Cited Findings
- `.equ MOTOR_BRAKE = 0 ; Enable brake during neutral/idle ("motor drag" brake)` and `.equ LOW_BRAKE = 0 ; Enable brake on very short RC pulse`, both unconditional. — [tgy.asm L183-184](https://github.com/sim-/tgy/blob/master/tgy.asm#L183)
- `MIN_DUTY = 56 * CPU_MHZ / 16`. `POWER_RANGE = 800 * CPU_MHZ / 16 + MIN_DUTY`, which is 856 at 16 MHz. `PWR_COOL_START = POWER_RANGE/24`. `PWR_MIN_START = POWER_RANGE/6 ; Power limit while starting (to start)`. `PWR_MAX_START = POWER_RANGE/4 ; Power limit while starting (if still not running)`. `PWR_MAX_RPM1 = /4`, `PWR_MAX_RPM2 = /2`. — [tgy.asm L235-250](https://github.com/sim-/tgy/blob/master/tgy.asm#L235)
- Start: `ldi2 YL, YH, PWR_MIN_START ; Start with limited power…` into `sys_control`. `set_new_duty` limits duty to `timing_duty` and `sys_control` ("Limit duty to sys_control"). During startup `sys_control` is raised in steps of POWER_RANGE/48 up to PWR_MAX_START. After `ENOUGH_GOODIES = 12` good commutations it ramps to MAX_POWER. If start attempts continue, power is modulated down to `PWR_COOL_START` and eventually the ESC gives up with the "start failed" f4 beacon. — [tgy.asm L2916-2925, L3586-3587, L3797-3832](https://github.com/sim-/tgy/blob/master/tgy.asm#L3586)
- Start is triggered by any non-zero `rc_duty`: `wait_for_power_rx … adiw YL,0; brne start_from_running`. — [tgy.asm L3572-3576](https://github.com/sim-/tgy/blob/master/tgy.asm#L3572)
- `rc_do_scale` offsets every non-zero result by `MIN_DUTY` ("Offset result so that 0 is MIN_DUTY") and clamps to MAX_POWER. — [tgy.asm L2581-2585](https://github.com/sim-/tgy/blob/master/tgy.asm#L2581)
- Without MOTOR_BRAKE, the ESC returns to idle (`restart_control`) if a commutation times out with power off. — [tgy.asm L3782-3788](https://github.com/sim-/tgy/blob/master/tgy.asm#L3782)

### Inferences
- What changes the start threshold is the calibrated low value (about 17/16 × the measured minimum) or the 1060 µs default, not PWR_MIN_START. Just above that threshold the commanded duty is about MIN_DUTY (about 6.5%). That may be too little to spin a 2212-class motor with a prop, so the motor can sit and twitch or try to start until throttle rises. Start power is then capped at about 16.6% (PWR_MIN_START), rising to 25% (PWR_MAX_START) until it is running. So a commanded throttle above about 25% does not add starting torque until the motor is synchronised.
- This interacts with the user's noted "15% start throttle". About 15% stick on a calibrated 1000-2000 µs range is about 1150 µs, which maps to roughly MIN_DUTY + about 10% of the scaled range (about 16% duty). That is close to the PWR_MIN_START cap, which plausibly explains why about 15% is where starts become reliable. This is an inference, not measured.

### Gaps
- I did not verify whether specific cheap "SimonK 30A" units ship custom builds with MOTOR_BRAKE, COMP_PWM or a different MOTOR_ADVANCE (upstream default 18°). Check the vendor listing or read the flash back via the boot loader to confirm.
- I found no forum or primary-source statement from sim- tying PWR_MIN_START to a perceived "start throttle". The relationship above is derived from code only.
