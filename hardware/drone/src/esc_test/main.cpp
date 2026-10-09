// ESC control for 4x SimonK 30A ESC + 2212 1000KV motors.
// Wiring: ESC white (signal) -> GPIO 13 / 32 / 26 / 27 (motors 1-4),
//         ESC black -> GND, ESC red (BEC 5V) unconnected.
//
// Serial commands (115200 baud, newline-terminated):
//   N       set all motors to N percent (0 = off; 1..IDLE_PCT is raised to IDLE_PCT;
//           clamped to MAX_THROTTLE_PCT)
//   M N     set motor M (1-4) to N percent, e.g. "2 20"
//   s       stop all motors immediately
//   ?       print current status
//   cal     ESC throttle-range calibration (battery DISCONNECTED, props OFF):
//           outputs go to full throttle; connect the battery and press Enter at the
//           same moment; full throttle is held CAL_MAX_HOLD_MS, then minimum.

#include <Arduino.h>

constexpr int NUM_MOTORS = 4;
constexpr int ESC_PINS[NUM_MOTORS] = {13, 32, 26, 27};
// Disabled outputs stay at minimum throttle. (Motor 2 re-enabled after replacing the motor with a snapped phase wire.)
constexpr bool MOTOR_ENABLED[NUM_MOTORS] = {true, true, true, true};
constexpr int PWM_FREQ_HZ = 50;           // standard servo-style ESC signal, 20 ms period
constexpr int PWM_RES_BITS = 16;
constexpr int MIN_PULSE_US = 1000;        // zero throttle / arming
constexpr int MAX_PULSE_US = 2000;        // full throttle
constexpr int MAX_THROTTLE_PCT = 50;      // bench safety cap; raise deliberately
// Lowest running throttle: just above the slowest motor's reliable start (~15% with props).
// Like a flight controller's min_throttle / motor idle; any non-zero command is raised to this.
constexpr int IDLE_PCT = 17;
constexpr int RAMP_STEP_PCT = 1;               // max change per ramp tick
constexpr uint32_t RAMP_UP_INTERVAL_MS = 120;  // => idle to 50% in ~4 s; slow to limit current spikes
constexpr uint32_t RAMP_DOWN_INTERVAL_MS = 20; // => 50% to idle in ~0.7 s
constexpr uint32_t ARM_TIME_MS = 3000;
// Calibration timing: SimonK needs <1 s at max; Hobbywing-style firmware enters its
// programming menu if max is held ~7 s after power-up, so hold 3 s and then drop.
constexpr uint32_t CAL_MAX_HOLD_MS = 3000;
constexpr uint32_t CAL_MIN_HOLD_MS = 6000;

enum CalState { CAL_OFF, CAL_WAIT_BATTERY, CAL_HOLD_MAX, CAL_HOLD_MIN };

int targetPct[NUM_MOTORS] = {};
int currentPct[NUM_MOTORS] = {};
CalState calState = CAL_OFF;
uint32_t calStateMs = 0;

void writePulseUs(int motor, int us) {
  const uint32_t periodUs = 1000000UL / PWM_FREQ_HZ;
  const uint32_t duty = ((uint32_t)us * ((1UL << PWM_RES_BITS) - 1)) / periodUs;
  ledcWrite(motor, duty);  // LEDC channel == motor index
}

int lastPulseUs[NUM_MOTORS] = {};

void writePulseIfChanged(int motor, int us) {
  // Only touch the LEDC hardware when the pulse width actually changes.
  if (us == lastPulseUs[motor]) return;
  lastPulseUs[motor] = us;
  writePulseUs(motor, us);
}

void applyThrottle(int motor, int pct) {
  writePulseIfChanged(motor, MIN_PULSE_US + (MAX_PULSE_US - MIN_PULSE_US) * pct / 100);
}

void stopAll() {
  for (int m = 0; m < NUM_MOTORS; m++) {
    targetPct[m] = currentPct[m] = 0;
    applyThrottle(m, 0);
  }
}

// 0 stays 0 (off); anything else is clamped to [IDLE_PCT, MAX_THROTTLE_PCT].
int clampThrottle(long pct) {
  if (pct <= 0) return 0;
  return constrain((int)pct, IDLE_PCT, MAX_THROTTLE_PCT);
}

void printStatus() {
  for (int m = 0; m < NUM_MOTORS; m++) {
    Serial.printf("motor %d (GPIO %d): target=%d%% current=%d%%%s\n",
                  m + 1, ESC_PINS[m], targetPct[m], currentPct[m],
                  MOTOR_ENABLED[m] ? "" : " [disabled]");
  }
  Serial.printf("idle %d%%, cap %d%%\n", IDLE_PCT, MAX_THROTTLE_PCT);
}

bool isNumber(const String &s) {
  if (s.isEmpty()) return false;
  for (char c : s) {
    if (!isDigit(c)) return false;
  }
  return true;
}

void abortCalibration() {
  calState = CAL_OFF;
  stopAll();
  Serial.println("Calibration aborted, minimum throttle sent. Disconnect the battery before retrying.");
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.isEmpty()) return;
  if (cmd == "s" || cmd == "S") {
    stopAll();
    Serial.println("STOP");
    return;
  }
  if (cmd == "?") {
    printStatus();
    return;
  }
  if (cmd == "cal") {
    stopAll();
    for (int m = 0; m < NUM_MOTORS; m++) {
      if (MOTOR_ENABLED[m]) writePulseIfChanged(m, MAX_PULSE_US);
    }
    calState = CAL_WAIT_BATTERY;
    calStateMs = millis();
    Serial.println("CALIBRATION: outputs now at FULL throttle (2000 us).");
    Serial.println("  The battery must be DISCONNECTED and props OFF. If it is connected, press 's' NOW.");
    Serial.println("  Connect the battery and press Enter at the same moment.");
    Serial.printf("  Full throttle is then held %lu s, then minimum automatically. ('s' aborts.)\n",
                  CAL_MAX_HOLD_MS / 1000);
    return;
  }

  const int space = cmd.indexOf(' ');
  if (space < 0 && isNumber(cmd)) {
    const int pct = clampThrottle(cmd.toInt());
    for (int m = 0; m < NUM_MOTORS; m++) {
      if (MOTOR_ENABLED[m]) targetPct[m] = pct;
    }
    printStatus();
    return;
  }
  if (space > 0) {
    String motorStr = cmd.substring(0, space);
    String pctStr = cmd.substring(space + 1);
    pctStr.trim();
    if (isNumber(motorStr) && isNumber(pctStr)) {
      const int motor = motorStr.toInt();
      if (motor >= 1 && motor <= NUM_MOTORS) {
        if (!MOTOR_ENABLED[motor - 1]) {
          Serial.printf("motor %d is disabled\n", motor);
          return;
        }
        targetPct[motor - 1] = clampThrottle(pctStr.toInt());
        printStatus();
        return;
      }
    }
  }
  Serial.println("unknown command; use N, M N (motor 1-4), s, ?, or cal");
}

// Advances the timed part of calibration. Returns true while calibration owns the outputs.
bool updateCalibration() {
  const uint32_t elapsed = millis() - calStateMs;
  switch (calState) {
    case CAL_OFF:
      return false;
    case CAL_WAIT_BATTERY:
      return true;
    case CAL_HOLD_MAX:
      if (elapsed >= CAL_MAX_HOLD_MS) {
        stopAll();
        calState = CAL_HOLD_MIN;
        calStateMs = millis();
        Serial.printf("Minimum throttle sent. Holding %lu s - count the beeps:\n", CAL_MIN_HOLD_MS / 1000);
        Serial.println("  2 beeps + long beep = SimonK; 3 short (3S cells) + long beep = Hobbywing-style.");
      }
      return true;
    case CAL_HOLD_MIN:
      if (elapsed >= CAL_MIN_HOLD_MS) {
        calState = CAL_OFF;
        Serial.println("Calibration done. Disconnect the battery, wait a few seconds, reconnect it.");
      }
      return true;
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  for (int m = 0; m < NUM_MOTORS; m++) {
    ledcSetup(m, PWM_FREQ_HZ, PWM_RES_BITS);
    ledcAttachPin(ESC_PINS[m], m);
    applyThrottle(m, 0);
  }

  Serial.println("\nESC controller: arming 4 motors at minimum throttle...");
  delay(ARM_TIME_MS);
  Serial.println("Armed. Commands: N (all), M N (motor 1-4), s (stop), ? (status), cal.");
}

void loop() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    const bool eol = (c == '\n' || c == '\r');

    if (calState != CAL_OFF) {
      if (c == 's' || c == 'S') {
        line = "";
        abortCalibration();
      } else if (calState == CAL_WAIT_BATTERY && eol && millis() - calStateMs > 1000) {
        // The 1 s guard skips the line ending that followed "cal" itself.
        calState = CAL_HOLD_MAX;
        calStateMs = millis();
        Serial.printf("Holding full throttle for %lu s...\n", CAL_MAX_HOLD_MS / 1000);
      }
      continue;  // other input is ignored during calibration
    }

    if (eol) {
      handleCommand(line);
      line = "";
    } else if (c == 's' || c == 'S') {
      // Stop acts on the keypress, without waiting for Enter.
      line = "";
      handleCommand("s");
    } else if (line.length() < 16) {
      line += c;
    }
  }

  if (updateCalibration()) return;

  static uint32_t lastRampUp = 0;
  static uint32_t lastRampDown = 0;
  const uint32_t now = millis();
  const bool upTick = now - lastRampUp >= RAMP_UP_INTERVAL_MS;
  const bool downTick = now - lastRampDown >= RAMP_DOWN_INTERVAL_MS;
  if (upTick) lastRampUp = now;
  if (downTick) lastRampDown = now;
  for (int m = 0; m < NUM_MOTORS; m++) {
    int &cur = currentPct[m];
    const int target = targetPct[m];
    if (target > 0 && cur < IDLE_PCT) {
      cur = IDLE_PCT;  // jump straight from off to idle, skipping the no-start zone
    } else if (target == 0 && cur > 0 && cur <= IDLE_PCT) {
      cur = 0;         // below idle there is nothing useful; switch off
    } else if (upTick && cur < target) {
      cur = min(cur + RAMP_STEP_PCT, target);
    } else if (downTick && cur > target) {
      cur = max(cur - RAMP_STEP_PCT, target);
    }
    applyThrottle(m, cur);
  }
}
