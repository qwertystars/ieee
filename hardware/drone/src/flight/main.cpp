// Manual flight controller for the ESP32 quad (4x ESC + 2212 motors, MPU6050 telemetry).
//
// The flight loop runs at 250 Hz in its own high-priority task:
//   Phone throttle + manual roll/pitch/yaw motor offsets -> mixer -> ESCs.
// MPU6050 angles are used only for telemetry and tilt cutoffs, never motor corrections.
// The phone connects to the "esp32-drone" WiFi network and opens http://192.168.4.1/.
//
// Safety: arming needs throttle at 0 and the drone roughly level. The motors cut if the phone
// link drops for LINK_TIMEOUT_MS, the drone tilts past CRASH_ANGLE_DEG, the IMU stops answering,
// or STOP is pressed (phone button, or 's' over serial).
//
// Serial commands (115200 baud):
//   s              disarm immediately
//   imu            toggle a 10 Hz stream of angles, gyro rates and accel (for checking the IMU orientation)
//   level          redo gyro + level calibration (disarmed, drone still on a level surface)
//   bench PCT      arm without the phone and hold a base throttle of PCT % (17..50), PROPS OFF;
//                  all motors receive equal throttle. Stops after BENCH_MAX_MS or on 's'.

#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>

#include "config.h"
#include "imu.h"
#include "web_page.h"

// ---- Shared state ----
// Written by the web handlers (loop task), read by the flight task.
struct Control {
  float throttle = 0;  // 0..1 from the phone's throttle strip
  float roll = 0;      // -1..1, + = right
  float pitch = 0;     // -1..1, + = forward
  float yaw = 0;       // -1..1, + = spin nose right (clockwise from above)
  uint32_t lastMsgMs = 0;
  bool armRequest = false;
  bool disarmRequest = false;
  bool levelRequest = false;
};
Control ctl;
portMUX_TYPE ctlMux = portMUX_INITIALIZER_UNLOCKED;

// Written by the flight task, read elsewhere for telemetry.
volatile bool armed = false;
volatile bool imuReady = false;
volatile float telRoll = 0, telPitch = 0;
volatile float telRate[3] = {};
volatile float telAccel[3] = {};
volatile float telMotor[NUM_MOTORS] = {};
volatile uint32_t telLoops = 0, telImuErrors = 0;
volatile float telBase = 0;
const char *volatile lastEvent = "starting";

Mpu6050 imu;
WebServer server(80);

// ---- Motors ----
void writeMotor(int m, float throttle) {
  telMotor[m] = throttle;
  const uint32_t us = MIN_PULSE_US + (uint32_t)(constrain(throttle, 0.0f, 1.0f) * (MAX_PULSE_US - MIN_PULSE_US));
  const uint32_t periodUs = 1000000UL / ESC_PWM_HZ;
  ledcWrite(m, us * 65535UL / periodUs);  // LEDC channel == motor index
}

void motorsOff() {
  for (int m = 0; m < NUM_MOTORS; m++) writeMotor(m, 0);
}

// ---- Flight task ----
float roll = 0, pitch = 0;          // degrees; + = right side down / nose up
float levelRoll = 0, levelPitch = 0; // accelerometer angles when sitting level, subtracted out
float baseThrottle = 0;
int imuErrors = 0;

// Accelerometer-only angles; valid when the drone isn't accelerating hard.
void accelAngles(const ImuSample &s, float &r, float &p) {
  r = atan2f(-s.accel[1], -s.accel[2]) * RAD_TO_DEG;
  p = atan2f(s.accel[0], sqrtf(s.accel[1] * s.accel[1] + s.accel[2] * s.accel[2])) * RAD_TO_DEG;
}

// Gyro bias + level reference. The drone must be still on a level surface.
bool calibrate() {
  if (!imu.calibrateGyro(500)) return false;
  float sumR = 0, sumP = 0;
  const int n = 200;
  for (int i = 0; i < n; i++) {
    ImuSample s;
    if (!imu.read(s)) return false;
    // Sitting still, the accelerometer must see 1 g of gravity; zeros mean the sensor isn't measuring.
    const float g = sqrtf(s.accel[0] * s.accel[0] + s.accel[1] * s.accel[1] + s.accel[2] * s.accel[2]);
    if (g < 0.8f || g > 1.2f) {
      Serial.printf("Calibration: accel reads %.2f g, expected ~1 g\n", g);
      return false;
    }
    float r, p;
    accelAngles(s, r, p);
    sumR += r;
    sumP += p;
    delay(2);
  }
  levelRoll = sumR / n;
  levelPitch = sumP / n;
  roll = pitch = 0;
  Serial.printf("Calibrated: level offset roll %.1f pitch %.1f deg\n", levelRoll, levelPitch);
  return true;
}

void disarm(const char *why) {
  if (armed) Serial.printf("DISARMED: %s\n", why);
  armed = false;
  lastEvent = why;
  motorsOff();
}

void resetThrottle() {
  baseThrottle = 0;
}

void flightStep(float dt) {
  Control c;
  portENTER_CRITICAL(&ctlMux);
  c = ctl;
  ctl.armRequest = ctl.disarmRequest = ctl.levelRequest = false;
  portEXIT_CRITICAL(&ctlMux);

  if (c.disarmRequest) disarm("STOP pressed");

  if (c.levelRequest && !armed) {
    lastEvent = calibrate() ? "level calibrated" : "level failed: keep still";
  }

  telLoops++;
  ImuSample s;
  if (!imu.read(s)) {
    telImuErrors++;
    if (++imuErrors >= 10) disarm("IMU not responding");
    return;
  }
  imuErrors = 0;

  // Attitude: integrate the gyro, gently pull towards the accelerometer's idea of level.
  roll += s.gyro[0] * dt;
  pitch += s.gyro[1] * dt;
  const float g = sqrtf(s.accel[0] * s.accel[0] + s.accel[1] * s.accel[1] + s.accel[2] * s.accel[2]);
  if (g > 0.85f && g < 1.15f) {
    float accRoll, accPitch;
    accelAngles(s, accRoll, accPitch);
    roll = COMP_FILTER_ALPHA * roll + (1 - COMP_FILTER_ALPHA) * (accRoll - levelRoll);
    pitch = COMP_FILTER_ALPHA * pitch + (1 - COMP_FILTER_ALPHA) * (accPitch - levelPitch);
  }
  telRoll = roll;
  telPitch = pitch;
  for (int i = 0; i < 3; i++) {
    telRate[i] = s.gyro[i];
    telAccel[i] = s.accel[i];
  }

  const bool linkOk = millis() - c.lastMsgMs < LINK_TIMEOUT_MS;

  if (!armed && c.armRequest) {
    if (c.throttle >= THROTTLE_DEADBAND) {
      lastEvent = "arm refused: throttle not at 0";
    } else if (fabsf(roll) > ARM_MAX_TILT_DEG || fabsf(pitch) > ARM_MAX_TILT_DEG) {
      lastEvent = "arm refused: not level";
    } else if (!linkOk) {
      lastEvent = "arm refused: no link";
    } else {
      resetThrottle();
      armed = true;
      lastEvent = "armed";
      Serial.println("ARMED");
    }
  }

  if (!armed) {
    motorsOff();
    telBase = 0;
    return;
  }
  if (!linkOk) return disarm("phone link lost");
  if (fabsf(roll) > CRASH_ANGLE_DEG || fabsf(pitch) > CRASH_ANGLE_DEG) return disarm("tilted too far");

  if (c.throttle < THROTTLE_DEADBAND) {
    // Armed on the ground: spin at idle, no corrections, nothing winding up.
    resetThrottle();
    for (int m = 0; m < NUM_MOTORS; m++) writeMotor(m, IDLE_THROTTLE);
    telBase = IDLE_THROTTLE;
    return;
  }

  const float target = IDLE_THROTTLE + c.throttle * (MAX_THROTTLE - IDLE_THROTTLE);
  baseThrottle = max(baseThrottle, IDLE_THROTTLE);
  baseThrottle = target > baseThrottle ? min(target, baseThrottle + THROTTLE_RISE_PER_S * dt) : target;
  telBase = baseThrottle;

  // Manual motor offsets only: sensor readings never feed the mixer.
  // Pad forward = nose down; centred pad gives equal throttle on all motors.
  const float outRoll = c.roll * MANUAL_MIX_LIMIT;
  const float outPitch = -c.pitch * MANUAL_MIX_LIMIT;
  const float outYaw = c.yaw * MANUAL_YAW_LIMIT;

  for (int m = 0; m < NUM_MOTORS; m++) {
    const float out = baseThrottle + MIX[m].roll * outRoll + MIX[m].pitch * outPitch + MIX[m].yaw * outYaw;
    writeMotor(m, constrain(out, IDLE_THROTTLE, MAX_THROTTLE));
  }
}

void flightTask(void *) {
  while (!imu.begin()) {
    lastEvent = "MPU6050 not found: check wiring";
    Serial.println("MPU6050 not found on I2C (SDA 21, SCL 22). Retrying...");
    delay(1000);
  }
  Serial.printf("MPU6050 found (WHO_AM_I 0x%02X)\n", imu.whoAmI());
  while (!calibrate()) {
    lastEvent = "calibrating: keep the drone still";
    Serial.println("Calibration failed (drone moved?). Keep it still and level. Retrying...");
    delay(500);
  }
  imuReady = true;
  lastEvent = "ready";

  const TickType_t period = pdMS_TO_TICKS(1000 / LOOP_HZ);
  TickType_t lastWake = xTaskGetTickCount();
  uint32_t lastUs = micros();
  for (;;) {
    vTaskDelayUntil(&lastWake, period);
    const uint32_t nowUs = micros();
    float dt = (nowUs - lastUs) * 1e-6f;
    lastUs = nowUs;
    if (dt <= 0 || dt > 0.05f) dt = 1.0f / LOOP_HZ;
    flightStep(dt);
  }
}

// ---- Web control ----
void sendTelemetry() {
  char buf[160];
  snprintf(buf, sizeof buf, "{\"armed\":%s,\"roll\":%.2f,\"pitch\":%.2f,\"base\":%.2f,\"msg\":\"%s\"}",
           armed ? "true" : "false", telRoll, telPitch, telBase, lastEvent);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", buf);
}

void handleControl() {
  const float t = constrain(server.arg("t").toFloat(), 0.0f, 1.0f);
  const float r = constrain(server.arg("r").toFloat(), -1.0f, 1.0f);
  const float p = constrain(server.arg("p").toFloat(), -1.0f, 1.0f);
  const float y = constrain(server.arg("y").toFloat(), -1.0f, 1.0f);  // absent (touch page) = 0
  portENTER_CRITICAL(&ctlMux);
  ctl.throttle = t;
  ctl.roll = r;
  ctl.pitch = p;
  ctl.yaw = y;
  ctl.lastMsgMs = millis();
  portEXIT_CRITICAL(&ctlMux);
  sendTelemetry();
}

void handleArm() {
  portENTER_CRITICAL(&ctlMux);
  ctl.armRequest = imuReady;
  ctl.lastMsgMs = millis();
  portEXIT_CRITICAL(&ctlMux);
  delay(20);  // let the flight task act on it so the reply shows the result
  sendTelemetry();
}

void requestDisarm() {
  portENTER_CRITICAL(&ctlMux);
  ctl.disarmRequest = true;
  ctl.throttle = 0;
  portEXIT_CRITICAL(&ctlMux);
}

void handleStop() {
  requestDisarm();
  delay(20);
  sendTelemetry();
}

// ---- Serial commands ----
bool streamImu = false;

// ---- Bench mode: arm from serial and hold a throttle, standing in for the phone ----
bool benching = false;
float benchStick = 0;
uint32_t benchEndMs = 0;

void startBench(float pct) {
  if (!imuReady) return (void)Serial.println("IMU not ready");
  if (armed) return (void)Serial.println("already armed");
  pct = constrain(pct, IDLE_THROTTLE * 100, MAX_THROTTLE * 100);
  benchStick = (pct / 100 - IDLE_THROTTLE) / (MAX_THROTTLE - IDLE_THROTTLE);
  portENTER_CRITICAL(&ctlMux);
  ctl.throttle = 0;  // arming needs zero throttle; benchService raises it once armed
  ctl.roll = ctl.pitch = ctl.yaw = 0;  // bench mode always drives equal motor throttle
  ctl.armRequest = true;
  ctl.lastMsgMs = millis();
  portEXIT_CRITICAL(&ctlMux);
  delay(20);
  if (!armed) return (void)Serial.printf("bench not started: %s\n", lastEvent);
  benching = true;
  benchEndMs = millis() + BENCH_MAX_MS;
  Serial.printf("BENCH: base throttle %.0f%%, motors capped at %.0f%%. 's' + Enter stops.\n", pct,
                MAX_THROTTLE * 100);
}

void benchService() {
  if (!benching) return;
  if (!armed) {
    benching = false;
    Serial.printf("bench ended: %s\n", lastEvent);
    return;
  }
  if (millis() > benchEndMs) {
    benching = false;
    requestDisarm();
    Serial.println("bench ended: time limit");
    return;
  }
  portENTER_CRITICAL(&ctlMux);
  ctl.throttle = benchStick;
  ctl.lastMsgMs = millis();
  portEXIT_CRITICAL(&ctlMux);
}

void handleSerialCommand(String cmd) {
  cmd.trim();
  if (cmd.isEmpty()) return;
  if (cmd == "imu") {
    streamImu = !streamImu;
    return;
  }
  if (cmd.startsWith("bench ")) return startBench(cmd.substring(6).toFloat());
  if (cmd == "level") {
    if (armed) return (void)Serial.println("disarm first");
    portENTER_CRITICAL(&ctlMux);
    ctl.levelRequest = true;
    portEXIT_CRITICAL(&ctlMux);
    Serial.println("Recalibrating: keep the drone still and level...");
    return;
  }
  Serial.println("commands: s, imu, level, bench PCT");
}

void pollSerial() {
  static String line;
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == 's' && line.isEmpty()) {
      // Stop acts on the keypress, without waiting for Enter.
      benching = false;
      requestDisarm();
      Serial.println("STOP");
      line = "#";  // swallow the rest of this line
    } else if (c == '\n' || c == '\r') {
      if (line != "#") handleSerialCommand(line);
      line = "";
    } else if (line.length() < 40) {
      line += c;
    }
  }
}

// ---- Setup / loop ----
void setup() {
  // ESCs first, so they see "zero throttle" as soon as possible after power-up.
  for (int m = 0; m < NUM_MOTORS; m++) {
    ledcSetup(m, ESC_PWM_HZ, 16);
    ledcAttachPin(ESC_PINS[m], m);
  }
  motorsOff();

  Serial.begin(115200);
  Serial.println("\nFlight controller starting. Keep the drone still and level.");

  WiFi.softAP(WIFI_SSID, WIFI_PASS);
  server.on("/", [] { server.send_P(200, "text/html", WEB_PAGE); });
  server.on("/c", handleControl);
  server.on("/arm", handleArm);
  server.on("/stop", handleStop);
  server.begin();
  Serial.printf("WiFi \"%s\" (password \"%s\"), open http://%s/\n", WIFI_SSID, WIFI_PASS,
                WiFi.softAPIP().toString().c_str());

  // Above the loop task (priority 1) on the same core, so web requests never delay the control loop.
  xTaskCreatePinnedToCore(flightTask, "flight", 4096, nullptr, 5, nullptr, 1);
}

void loop() {
  server.handleClient();
  pollSerial();
  benchService();

  static uint32_t lastPrint = 0;
  if (streamImu && millis() - lastPrint >= 100) {
    lastPrint = millis();
    Serial.printf("roll %6.1f  pitch %6.1f  | rate roll %7.1f pitch %7.1f yaw %7.1f  | accel %5.2f %5.2f %5.2f | motors %2.0f %2.0f %2.0f %2.0f | loops %lu err %lu %s\n",
                  telRoll, telPitch, telRate[0], telRate[1], telRate[2], telAccel[0], telAccel[1], telAccel[2],
                  telMotor[0] * 100, telMotor[1] * 100, telMotor[2] * 100, telMotor[3] * 100, telLoops, telImuErrors, armed ? "ARMED" : "");
  }
  delay(1);
}
