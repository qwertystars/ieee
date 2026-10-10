# Calibrating hobby PWM ESCs (especially SimonK 30A) from a microcontroller (ESP32 / Arduino)

Research method note: all web access was through TinyFish search/fetch (MCP and CLI). Two raw source files (SimonK `tgy.asm` and ArduPilot `esc_calibration.cpp`) could not be fetched by TinyFish (`target_unreachable` for raw.githubusercontent.com), so they were downloaded with `curl` as plain file downloads and read locally. Line references below are to those files at their current `master`.

---

## 1. Step-by-step procedures and timings from reputable sources

### Takeaway
Every source uses the same basic sequence: send max throttle *before* the ESC is powered, power the ESC, wait for the "max captured" beep(s), switch to min, and wait for the "min captured" beep(s). The exact firmware matters for timing. SimonK learns the high pulse right after its power-up beeps by averaging about 31 pulses (roughly 0.6 s at 50 Hz). The input then has to drop below the learned high, settle, and stay stable for 32 more pulses, and the values are written to EEPROM. Hobbywing-style stock firmware confirms max about 2 s after power-up and **enters programming mode if max is held about 5 s longer**. BLHeli_S needs max held for 3 s and min held for 3 s. ArduPilot's automatic routine holds max for 5 s and then holds min indefinitely.

### Cited Findings

**SimonK (tgy) firmware, the primary source for "SimonK 30A" ESCs**
- The default throttle range is stop at 1060 µs and full throttle at 1860 µs. These defaults are used if no calibration has been saved to EEPROM. — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md)
- Boards without an external oscillator (typically flashed with `tgy.hex`) use the ATmega8 internal RC oscillator. It "may be off by 5% - 10% between each board, and will also drift by 10% or more over a 40 degree Celsius temperature range". This can cause throttle differences between ESCs and arming problems in the cold, which is why calibration is recommended. — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md)
- As an alternative to calibrating, ESCs *with external resonators* can use the defaults directly (for example Baseflight `minthrottle=1064`, `maxthrottle=1864`). — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md)
- **Entry condition:** the input pulse must be at or above `PROGRAM_RC_PULS`, which defaults to 1460 µs, to enter programming mode. This "will differ slightly on boards with no external oscillator". — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md). In source, `PROGRAM_RC_PULS = (STOP_RC_PULS + FULL_RC_PULS)/2 ; Normally 1460` (tgy.asm line ~224) — [tgy.asm](https://github.com/sim-/tgy/blob/master/tgy.asm)
- **Official SimonK beep sequence:** "power up the ESC and wait for a single beep after the typical rising initialization beeps. This indicates the high pulse length has been saved to RAM. Move the stick or knob to the lowest setting, and wait for two beeps. This indicates that the low pulse length has been saved to RAM... If the stick is not moved after the final setting, the ESC should now write the RAM settings to EEPROM, and continue startup." The ESC then treats the same low pulse as a valid arming pulse. — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md)
  - Note that the README describes "single beep" and "two beeps" (beep_f3). Hobbywing-style manuals describe "beep-beep" for max and a long beep for min. Users of generic "SimonK 30A" ESCs may hear SimonK's pattern, not the Hobbywing pattern.
- **Timing details from the tgy.asm calibration routine (`rc_prog0`–`rc_prog_done`, lines ~2405–2474)** — [tgy.asm](https://github.com/sim-/tgy/blob/master/tgy.asm):
  - High-pulse learning averages `32 * 31/32` = 31 pulses. Low-pulse learning averages `32 * 17/16` = 34 pulses. At 50 Hz that is about 0.6–0.7 s of stable input per point.
  - During averaging, every pulse must stay within ±`MAX_DRIFT_PULS` = **10 µs** of the first pulse (line 231). Otherwise the routine runs `wait240ms` ("Wait for stick movement to settle") and starts the measurement over.
  - After the high point is captured, the routine loops until the pulse is *lower than the learned high*, then measures the low point. There is no fixed time-out in this loop, so there is no "move to min within N seconds" deadline as there is with Hobbywing firmware.
  - The routine stores the values to EEPROM (`rc_prog_done: rcall eeprom_write_block`) and rescales.
  - Margins of 1/16 on the low end and 1/32 on the high end are applied to the learned values "to try to avoid problems with arming and reaching full throttle during temperature extremes" — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md)
- **Calibration is only possible once, at arming time after a clean power-on reset.** `evaluate_rc_init` (which checks for programming mode) runs in the "wait for arming input" loop (`i_rc_puls1/2`, lines ~3435–3477). Arming then needs zero throttle for a count of 10 (`ldi temp1, 10 ; wait for this count of receiving power off`). — [tgy.asm](https://github.com/sim-/tgy/blob/master/tgy.asm)
- "There is currently no way to reset (remove) the calibration other than by clearing the EEPROM (or reflashing without EESAVE set)." — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md)
- Valid pulses must be between `MIN_RC_PULS = 768` µs and `MAX_RC_PULS = 2400` µs. Pulses outside that window are thrown away (tgy.asm lines 213–214). — [tgy.asm](https://github.com/sim-/tgy/blob/master/tgy.asm)

**Hobbywing (Skywalker / Quattro-style stock firmware; many generic "30A" ESCs copy this)**
- Throttle range setting: "Switch on the transmitter, move throttle stick to the top position. Connect battery pack to the ESC, and wait for about 2 seconds. The 'Beep-Beep-' tone should be emitted, means the top point of throttle range has been confirmed. Move throttle stick to the bottom position, several 'beep-' tones should be emitted to present the amount of battery cells. A long 'Beep-' tone should be emitted, means the lowest point of throttle range has been correctly confirmed." — [Hobbywing Skywalker Quattro manual](https://www.cmldistribution.co.uk/diagrams/HobbyWing/Skywalker%20Quattro%20Manual.pdf)
- **Program-mode trap:** with throttle at top at power-up, "Wait for 2 seconds, the motor should emit special tone like 'beep-beep-'. Wait for another 5 seconds, special tone... should be emitted, which means program mode is entered." So the window for dropping to min is roughly 2 s to 7 s after power-up. — [Hobbywing Skywalker Quattro manual](https://www.cmldistribution.co.uk/diagrams/HobbyWing/Skywalker%20Quattro%20Manual.pdf)
- Throttle signal loss protection: the ESC reduces power if the signal is lost for 1 s and cuts output after a further 2 s. — [Hobbywing Skywalker Quattro manual](https://www.cmldistribution.co.uk/diagrams/HobbyWing/Skywalker%20Quattro%20Manual.pdf)
- Oscar Liang quotes the same Hobbywing wording ("wait for about 2 seconds ... Beep-Beep ... Move throttle stick to the bottom ... long Beep"). His RC-receiver procedure says "Once the beeps finish, immediately drop the throttle to zero." — [Oscar Liang](https://oscarliang.com/how-to-calibrate-esc/)

**BLHeli_S (BLHeli-specific)**
- If 100% throttle is detected during the arming sequence, the ESC starts throttle calibration. "If throttle is above midstick for 3 seconds" → max stored; "If throttle is below midstick for 3 seconds" → min stored. The calibration range is 1000–2000 µs, and min/max must differ by more than 140 µs. Dshot disables calibration. — [BLHeli_S manual Rev16.x](https://bluerobotics.com/wp-content/uploads/2019/03/BLHeli_S-manual-SiLabs-Rev16.x.pdf)

**ArduPilot**
- Manual ESC-by-ESC: set throttle to max, connect LiPo, wait for "a musical tone then two beeps", lower the throttle to full down, and wait for cell-count beeps and then a long beep. — [ArduPilot Copter ESC calibration](https://ardupilot.org/copter/docs/esc-calibration.html)
- Semi-automatic (`ESC_CALIBRATION=3`): after power-up and the safety switch, "You will hear a musical tone then two beeps. A few seconds later you should hear a number of beeps... and finally a single long beep." — [ArduPilot Copter ESC calibration](https://ardupilot.org/copter/docs/esc-calibration.html)
- **Source timing for the auto routine:** `esc_calibration_auto()` outputs throttle 1.0 to all motors, refreshing about every 3 ms for **5000 ms**. It then outputs 0.0 in an infinite loop ("block until we restart"). Before that, it waits for the safety switch to be pressed. — [ArduPilot esc_calibration.cpp](https://github.com/ArduPilot/ardupilot/blob/master/ArduCopter/esc_calibration.cpp)
- Some ESCs do not allow calibration. For those, set the endpoints to about 1000/2000 (`MOT_PWM_MIN`=1000, `MOT_PWM_MAX`=2000). — [ArduPilot Copter ESC calibration](https://ardupilot.org/copter/docs/esc-calibration.html)

**Betaflight / BLHeliSuite (FC configurator)**
- Move the master slider to the top, connect the battery, and wait until "the motors stop beeping", then drag the slider to the bottom. Motors beep again to confirm. Calibrate with the protocol you will use (for example Multishot). Calibration is not needed for Dshot. — [Oscar Liang](https://oscarliang.com/how-to-calibrate-esc/)

**Arduino tutorials**
- lobodol/ESC-calibration (Servo library, 50 Hz, 1000–2000 µs, up to 4 ESCs on pins 4–7). Type "1" to send max, power the ESCs, hear "beep1 beep2 beep3", then "After 2sec, 'beep beep'... highest point confirmed". Type "0" to send min, hear cell-count beeps and then a long beep. It says it was written according to the HobbyKing ESC documentation. The Arduino is powered over USB, not from an ESC BEC. — [lobodol/ESC-calibration](https://github.com/lobodol/ESC-calibration)
- TechMonkeyBusiness calibrator. It sends max at boot, allows `delay(10000)` for the user to connect the battery, gives a 10 s red-LED warning, sends min and holds 10 s, then neutral for 10 s (the neutral step is for car ESCs). The default Servo range did not work for the author, so `ESC.attach(9,600,2250)` was used. "If the ESC beeps continuously, this means it is not detecting the maximum throttle signal." — [TechMonkeyBusiness](http://www.techmonkeybusiness.com/articles/ESC_Calibration_with_Arduino.html)

### Inferences
- For SimonK, a code-driven routine has to hold max steady (within ±10 µs) for at least ~1 s after the ESC's 3 rising power-up tones. It then has to drop to min and hold it steady for ≥ ~1 s plus the time to hear the beeps. Holding max longer does no harm on SimonK, because there is no programming-menu time-out. Long max holds are harmful on Hobbywing-style firmware (program mode after ~7 s), and BLHeli_S needs ≥ 3 s per point.
- A "universal" timing that satisfies SimonK, BLHeli_S and Hobbywing-style ESCs is: hold max for about **4–5 s after the ESC is powered**, then hold min for **≥ 4–5 s** (or indefinitely, as ArduPilot does). This is synthesized from the sources above, not stated by any one of them. The 5 s ArduPilot hold is near the upper limit for Hobbywing-style ESCs (2 s + 5 s = ~7 s before program mode), so 3–5 s is the safe band.

### Gaps
- I found no first-party manual for a specific SimonK-flashed "30A" product. Clone ESCs sold as "SimonK 30A" may run varied firmware builds (for example with BEACON or other compile-time options changed). Exact beep patterns may differ from the README.

---

## 2. Calibrating several ESCs at once (one pin vs. separate pins)

### Takeaway
Calibrating all ESCs at once is officially supported. ArduPilot's "all at once" mode simply sends the same PWM to every ESC, and Hobbywing sells a Y-hub for exactly this. Separate pins driven with identical values (lobodol sketch) also work. The pulse just has to be the same, and stable, on every ESC when each one powers up.

### Cited Findings
- "The All-at-once ESC calibration mode simply causes the autopilot to pass through the pilot's throttle directly through to the ESCs. If you power up the autopilot while in this mode you'll send the same PWM signal to all the ESCs. That's all it does." ArduPilot recommends trying all-at-once first, then the manual one-by-one method if it fails ("That should work almost every time"). — [ArduPilot Copter ESC calibration](https://ardupilot.org/copter/docs/esc-calibration.html)
- If, after calibration, motors don't start together or spin at the same speed, ArduPilot says to repeat the calibration or fall back to one-by-one. "Rarely after a full manual calibration you will also need to do an additional final automatic calibration." — [ArduPilot Copter ESC calibration](https://ardupilot.org/copter/docs/esc-calibration.html)
- Hobbywing: "The Throttle Signal HUB is recommended for calibrating the throttle ranges for 4 speed controllers simultaneously instead of one by one." The hub ties 4 ESC signal wires to one receiver channel. When the signal is distributed to several ESCs, only one BEC should stay connected: "the BECs in other ESCs must be disabled (That is, cut the red wires...)". — [Hobbywing Skywalker Quattro manual](https://www.cmldistribution.co.uk/diagrams/HobbyWing/Skywalker%20Quattro%20Manual.pdf)
- lobodol's sketch calibrates up to 4 ESCs at once on separate pins: "If you don't want to calibrate all ESCs at the time, you're free to connect them one by one... it doesn't make any difference." All ESC grounds are tied to the Arduino ground. — [lobodol/ESC-calibration](https://github.com/lobodol/ESC-calibration)
- SimonK calibrates each ESC to whatever pulse *that ESC* measures with its own oscillator. That is the point of calibration on internal-RC boards (5–10% board-to-board spread). — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md)
- SimonK warning about simultaneous calibration under brown-out: a weak pack caused a brown-out reset of all ESCs, and one ESC stored a new calibration. Since 2012-03-15, calibration is disabled after a brown-out reset. "When intentionally calibrating, be sure that you cleanly connect the power. If you don't hear the rising beeps, remove the power for a few seconds to allow the capacitors to discharge, then try again." — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md); source: `sbr flags0, (1<<NO_CALIBRATION)` on BORF — [tgy.asm](https://github.com/sim-/tgy/blob/master/tgy.asm)
- Symptom of uncalibrated or mismatched ESCs: with 4 generic 30A ESCs armed one after another (3 s each) without calibration, the motors started at different throttle values (28/29/30%) and ran at different speeds. — [Arduino forum "strange problem with 4 ESC's"](https://forum.arduino.cc/t/strange-problem-with-4-escs-and-4-motors/202208)

### Inferences
- Tying all signal wires to one GPIO is electrically fine for an ATmega input (high impedance, CMOS). The ESP32 pin then drives four inputs plus the wiring capacitance, which is still a light load. Use separate pins for flight anyway. For calibration, separate pins written with identical values are equivalent, provided all channels start outputting before the battery is connected.
- When all ESCs share one battery connector, connect it cleanly. A bouncy connection risks brown-out resets, and on SimonK the affected ESC would silently skip calibration.

### Gaps
- No source directly measured whether one ESP32 GPIO driving 4 ESC inputs in parallel degrades edges. This is an inference from the ATmega input characteristics.

---

## 3. Why calibration fails silently or ESCs keep beeping afterwards

### Takeaway
The usual causes are: max pulse not seen at power-up, or not above the entry threshold; an unstable or jittery pulse; a brown-out or unclean power-up (SimonK disables calibration); the signal line held as a constant high level rather than pulses (SimonK jumps to its bootloader); no common ground; holding max too long (Hobbywing program mode); and min not low enough to arm.

### Cited Findings
- **Not seeing max at power-up:** "If the ESC beeps continuously, this means it is not detecting the maximum throttle signal... you may need to change the signal pulse widths" (the author needed 600–2250 µs). — [TechMonkeyBusiness](http://www.techmonkeybusiness.com/articles/ESC_Calibration_with_Arduino.html)
- **SimonK entry threshold:** the input must be ≥ ~1460 µs (`PROGRAM_RC_PULS`) at the first valid pulses during arming, or programming is skipped and the ESC goes straight to normal arming evaluation (`rjmp evaluate_rc_puls ; Lower than PROGRAM_RC_PULS - exit programming`). — [tgy.asm](https://github.com/sim-/tgy/blob/master/tgy.asm)
- **Unstable pulse (jitter > ±10 µs):** the SimonK routine restarts with a 240 ms wait whenever drift exceeds `MAX_DRIFT_PULS` = 10 µs, so a noisy signal can loop forever without beeping. — [tgy.asm](https://github.com/sim-/tgy/blob/master/tgy.asm)
- **Brown-out / unclean power-up:** calibration is disabled after a brown-out reset, which the ESC signals with f3 f1 "dead cellphone" beeps instead of the f1 f2 f3 rising tones. — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md)
- **Signal line stuck HIGH (no pulses):** SimonK has `BOOT_JUMP = 1`: "long periods of high PWM input while disarmed will cause a jump to the boot loader". In source: "Wait 32 * 16 * 65536us (~2s) before jumping". If the input floats high, "Confusion may also result... touching the connector or connecting it later may drain the input and cause normal startup to occur, which may seem like the ESC is resetting". — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md); [tgy.asm](https://github.com/sim-/tgy/blob/master/tgy.asm)
- **No signal at all:** with no valid input while disarmed and BEACON enabled, SimonK emits an f3 beep after ~8 s and then every ~4 s. "If no input command is received for about 1 second, f3 f2 is beeped and the ESC returns to disarmed state." "fast repeating beeps of f4 while idle: Noise on PWM input detected." — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md)
- **Not arming after calibration (min too high):** "If you are unable to start the motor and are not hearing the forth, long beep, try lowering the throttle trim, or raise it all the way to start throttle calibration." — [SimonK tgy README](https://github.com/sim-/tgy/blob/master/README.md). ArduPilot: "try lowering your throttle trim 50%". — [ArduPilot](https://ardupilot.org/copter/docs/esc-calibration.html)
- **Microcontroller boot vs. ESC boot:** ArduPilot suggests "powering your ArduPilot board via the USB first to boot it up before plugging in the LiPo." — [ArduPilot](https://ardupilot.org/copter/docs/esc-calibration.html). lobodol powers the Arduino from USB and starts sending max *before* the ESCs get power. — [lobodol/ESC-calibration](https://github.com/lobodol/ESC-calibration)
- **Ground:** "Did you connect ground of your ESP32 with the ground of the powersupply of your ESC?" — [Arduino forum, ESP32 + ESC](https://forum.arduino.cc/t/using-esp32-to-move-brushless-motor-using-esc/1146131); lobodol: "Connect each ESC's ground to the Arduino's ground to make all having common ground." — [lobodol/ESC-calibration](https://github.com/lobodol/ESC-calibration)
- **Forgetting to arm / sending a non-zero first value:** an ESP32-S3 + SimonK 30A user saw no motor response. The cause was no arming phase. Adding `esc.writeMicroseconds(1000); delay(2000);` in `setup()` fixed it ("I forgot I need to ARM the BLDC motor"). — [Arduino forum, ESP32 + SimonK 30A level shifter](https://forum.arduino.cc/t/bldc-motor-not-responding-to-esp32-pwm-via-logic-level-shifter/1402897)
- **Holding max too long (Hobbywing-style firmware):** program mode is entered about 5 s after the 2-s "beep-beep". — [Hobbywing manual](https://www.cmldistribution.co.uk/diagrams/HobbyWing/Skywalker%20Quattro%20Manual.pdf). One Oscar Liang commenter's ESCs "enter calibration mode... but when I lower to minimum... they just beep 1, then 2, then 3 times and repeat". That pattern is consistent with a programming menu, though the commenter did not identify the cause. — [Oscar Liang comments](https://oscarliang.com/how-to-calibrate-esc/)
- **Need a power cycle:** ArduPilot ends with "disconnect the battery to exit ESC-calibration mode". After calibration, "unplugging and re-plugging the ESC will save the new settings" — [ArduPilot](https://ardupilot.org/copter/docs/esc-calibration.html); [Oscar Liang](https://oscarliang.com/how-to-calibrate-esc/). SimonK writes to EEPROM itself once the final point is held, without a power cycle. — [SimonK README](https://github.com/sim-/tgy/blob/master/README.md)
- **Motor required for tones:** "In order to get a tone from the ESC a motor must be connected." — [TechMonkeyBusiness](http://www.techmonkeybusiness.com/articles/ESC_Calibration_with_Arduino.html)

### Inferences
- In practice, a SimonK ESC that "keeps beeping" after a code-driven calibration is usually either beaconing (no valid pulses: wrong frequency or resolution, LEDC not attached, ground missing) or not arming (stored min higher than what the code later sends as idle). A good habit is to send the *same* min value in normal operation that was used during calibration.

### Gaps
- The robotshop and Arduino StackExchange calibration threads were blocked (bot_blocked / 403), so their anecdotes are not included.

---

## 4. ESP32-specific concerns

### Takeaway
A 3.3 V ESP32 signal technically meets the ATmega8's V_IH (0.6·VCC = 3.0 V at 5 V), but with only ~0.3 V of margin. It usually works, and a proper push-pull 5 V buffer (for example 74AHCT/74ACT) is the robust fix. Bidirectional MOSFET "I2C" level shifters are a poor choice. LEDC at 50 Hz has ample resolution. The real risks are API misuse (writing µs values as duty counts), strapping or boot-glitch pins, and an output that is high or floating before the code configures it.

### Cited Findings
- **ATmega8A input thresholds:** V_IH (except XTAL1/RESET) min = **0.6·VCC**; V_IL max = 0.2·VCC (VCC 2.7–5.5 V). At a 5 V ESC MCU supply, V_IH = 3.0 V. — [ATmega8A datasheet DS40001974B, DC characteristics](https://ww1.microchip.com/downloads/en/DeviceDoc/ATmega8A-Data-Sheet-DS40001974B.pdf)
- **Level shifter caution:** for an ESP32-S3 driving a SimonK 30A through a BSS138-style bidirectional 4-channel module, a forum member noted "Those shifters are basically designed for use with open drain signals like I2C. They may not be able to drive the signal input on the ESC" and suggested SN74ACT244N / SN74ACT241N buffers. (The OP's actual fault turned out to be missing arming.) — [Arduino forum](https://forum.arduino.cc/t/bldc-motor-not-responding-to-esp32-pwm-via-logic-level-shifter/1402897)
- Forum advice notes that 3.3 V "might be" insufficient for some ESCs that expect 5 V. This is hedged, not measured. — [Arduino forum](https://forum.arduino.cc/t/using-esp32-to-move-brushless-motor-using-esc/1146131). DeepBlue Embedded states "The PWM signal can be 3.3v or 5v logic level" for ESC control (STM32 context). — [DeepBlue Embedded (search snippet)](https://deepbluembedded.com/stm32-brushless-bldc-motor-control-stm32-esc-interfacing/)
- **LEDC / ESP32Servo:** ESP32Servo defaults to a 16-bit timer width (configurable 16–20) at 50 Hz. Its defaults are a min pulse of 544 µs and a max of 2400 µs if `attach(pin)` is used without limits, with enforced bounds of 500–2500 µs. It initializes servos at 1500 µs. Recommended pins: "2,4,12-19,21-23,25-27,32-33". — [ESP32Servo README](https://github.com/madhephaestus/ESP32Servo)
- In a forum post, a user configured LEDC at 50 Hz with 12-bit resolution and then called `ledcWrite(channel, 1000/2000)` with *microsecond* values (no conversion to duty counts), and motors didn't move. — [Arduino forum, ESP32 + ESC](https://forum.arduino.cc/t/using-esp32-to-move-brushless-motor-using-esc/1146131)
- **Strapping pins:** GPIO0 (pull-up), GPIO2 (pull-down), GPIO4 (pull-down), GPIO5 (pull-up), GPIO12/MTDI (pull-down), and GPIO15/MTDO (pull-up) have boot strapping functions and default pulls. External circuitry on them can change the boot mode, and their boot state can affect the external circuit. — [Kevin's blog, ESP32 strapping pins](https://emalliab.wordpress.com/2024/05/20/esp32-strapping-pins/) (summarising the ESP32 datasheet, section 3)
- Other reports of ESP32 pins glitching high at reset: ESP32-S3 GPIO20 held high ~175 ms after reset — [Arduino forum](https://forum.arduino.cc/t/esp32-s3-pin-20-is-always-high-after-start/1156286) (search snippet); "ESP32 GPIO pins are normally floating... at power up" — [Stack Overflow (snippet)](https://stackoverflow.com/questions/77303193/esp32-s3-gpio-num-21-briefly-goes-high-upon-boot-without-any-digitalwrite)
- Generic ESP32-C3: only 4 LEDC timers / 6 channels. Sharing a timer with another peripheral at another frequency can silently change a servo channel's frequency (servo ran at 10 kHz instead of 50 Hz). — [Seeed forum (snippet)](https://forum.seeedstudio.com/t/esp32c3-cannot-drive-a-servo-and-pwm-output-correctly/292547)

### Inferences
- **Resolution is not a problem:** at 50 Hz, a 16-bit LEDC tick is 20 000 µs / 65 536 ≈ 0.31 µs, and even 12-bit is ≈ 4.9 µs. Both are well inside SimonK's ±10 µs stability window. LEDC is a hardware timer, so jitter is negligible compared with that window. (This is my own arithmetic.)
- **3.3 V margin:** 3.3 V against a 3.0 V threshold leaves ~0.3 V. Ground offset between the ESP32 and ESC grounds (high current in a shared negative lead) eats directly into that margin. Run a dedicated signal-ground wire from each ESC's servo-lead ground to the ESP32 GND, and keep the signal and ground twisted. If an ESC behaves inconsistently, add a 74AHCT125/74ACT244-type buffer powered from 5 V.
- **Pin choice:** avoid strapping pins (0, 2, 4, 5, 12, 15) and pins that glitch at boot for ESC outputs. A boot glitch on a powered ESC is usually harmless on SimonK, because a short glitch isn't a valid 768–2400 µs pulse train. A pin that sits *high as a DC level* for ~2 s while the ESC waits for arming can trigger SimonK's BOOT_JUMP into the bootloader. Add a ~10 kΩ pull-down on each signal line so the line idles low while the ESP32 boots or resets (the SimonK README itself recommends a pull-down or load on the PWM input).
- **ESP32Servo defaults:** always call `attach(pin, 1000, 2000)` and `writeMicroseconds()`. Do not rely on `write(angle)` with the 544–2400 default mapping, because max would then be 2400 µs, at the edge of SimonK's `MAX_RC_PULS = 2400`. Note also that ESP32Servo emits 1500 µs immediately on attach. That is above SimonK's 1460 µs programming threshold, so attaching *after* the ESC is powered could start an unintended calibration. Write the intended value immediately after `attach()`, and attach before the ESC powers up.

### Gaps
- I found no oscilloscope-backed source quantifying LEDC jitter or rise time at 50 Hz.
- I found no source testing which specific "SimonK 30A" boards have an input series resistor or opto-isolation that would change the effective threshold.
- The Arduino-ESP32 core 3.x LEDC API changes (`ledcAttach(pin, freq, res)` replacing `ledcSetup` + `ledcAttachPin`) were not verified from a primary source in this session.

---

## 5. Recommended code structure for an automated calibration routine

### Takeaway
Use the ArduPilot / lobodol / TechMonkeyBusiness pattern. Start valid 50 Hz pulses at MAX *before* ESC power, prompt the user to connect the battery, hold MAX ~4–5 s (or until a button or serial confirm after "max captured" beeps), switch to MIN and hold ≥ 5 s (ArduPilot holds forever), then require a power cycle. Calibrate with exactly the endpoint values the flight code will use.

### Cited Findings (timing values used by sources)
- ArduPilot auto: MAX for 5000 ms (refreshed every ~3 ms), then MIN indefinitely until restart. — [ArduPilot esc_calibration.cpp](https://github.com/ArduPilot/ardupilot/blob/master/ArduCopter/esc_calibration.cpp)
- TechMonkeyBusiness: MAX at boot → 10 s for the user to connect the battery → 10 s LED warning → MIN for 10 s → (car only: neutral 10 s). The total MAX time *after* the battery is connected depends on when the user plugs in, so it is up to ~20 s, which would trip a Hobbywing program mode. That sketch targets car ESCs and SimonK-like behaviour. — [TechMonkeyBusiness](http://www.techmonkeybusiness.com/articles/ESC_Calibration_with_Arduino.html)
- lobodol: interactive serial. "1" = MAX, power the ESCs, wait for "beep beep" after ~2 s, "0" = MIN, wait for the long beep, "2" = test ramp. — [lobodol/ESC-calibration](https://github.com/lobodol/ESC-calibration)
- Hobbywing-style: max confirmed ~2 s after power-up, and you must leave MAX before ~7 s. — [Hobbywing manual](https://www.cmldistribution.co.uk/diagrams/HobbyWing/Skywalker%20Quattro%20Manual.pdf)
- BLHeli_S: ≥ 3 s above midstick, then ≥ 3 s below midstick. — [BLHeli_S manual](https://bluerobotics.com/wp-content/uploads/2019/03/BLHeli_S-manual-SiLabs-Rev16.x.pdf)
- SimonK: ~31 stable pulses for max after the power-up tones, then ~34 stable pulses for min after the input drops (±10 µs). Calibration only happens after a clean power-on reset. — [tgy.asm](https://github.com/sim-/tgy/blob/master/tgy.asm)
- Arming afterwards: send min for ~2 s before any throttle (forum fix for ESP32 + SimonK 30A). — [Arduino forum](https://forum.arduino.cc/t/bldc-motor-not-responding-to-esp32-pwm-via-logic-level-shifter/1402897)

### Inferences: suggested routine (synthesized; values chosen to satisfy all cited firmwares)
```
// Preconditions: PROPS OFF. ESP32 powered from USB (not from an ESC BEC). Battery disconnected.
// Common ground from every ESC signal-lead GND to ESP32 GND. ~10k pull-down on each signal pin.
const int PULSE_MIN = 1000, PULSE_MAX = 2000;   // use the SAME values in flight code

setup():
  for each ESC pin: attach(pin, PULSE_MIN, PULSE_MAX); writeMicroseconds(PULSE_MAX);  // immediately
  // Pulses are now valid 50 Hz at MAX on all channels before ESC power exists.
  prompt("Connect battery now, then press ENTER / button the instant you hear the rising tones");
  wait_for_user();                     // marks t0 = ESC power-up
  delay(4000);                         // SimonK: tones (~1 s) + ~0.6 s capture; Hobbywing: beep-beep at ~2 s;
                                       // BLHeli_S: 3 s; stays below Hobbywing's ~7 s program-mode limit
  // (alternative: wait for user confirming "max captured" beeps, but cap at ~5 s)
  for each ESC: writeMicroseconds(PULSE_MIN);
  delay(5000);                         // SimonK ~0.7 s + EEPROM; BLHeli_S 3 s; Hobbywing cell beeps + long beep
  prompt("Expect: SimonK 2 beeps then arm tone / Hobbywing cell-count + long beep. Disconnect battery.");
  keep sending PULSE_MIN forever (ArduPilot style) -- never stop pulses or drive the pin DC-high.

normal boot (separate firmware path / flag):
  attach + writeMicroseconds(PULSE_MIN) before ESC power if possible; hold MIN >= 2-3 s to arm;
  never output >= ~1460 us at power-up unless intentionally calibrating (SimonK program threshold).
```
- Gate calibration behind an explicit action (a jumper, a button held at boot, or a serial command), as TechMonkeyBusiness's "close a jumper" approach and ArduPilot's parameter flag do. A normal boot must never start at high throttle.
- If an ESC doesn't confirm, remove power for "a few seconds to allow the capacitors to discharge" before retrying (SimonK README), because brown-out resets block calibration.

### Gaps
- No source gives an authoritative, firmware-independent "hold max N seconds" value. The 4 s / 5 s figures above are a synthesis bounded by the Hobbywing program-mode window (~7 s), BLHeli_S's 3 s, and ArduPilot's 5 s.
