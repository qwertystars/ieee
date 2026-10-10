#pragma once
#include <Arduino.h>

// ---- Motors ----
// Seen from above, front pointing away:
//
//        FRONT
//   M4 (CW)    M2 (CCW)
//   GPIO 27    GPIO 32
//
//   M1 (CCW)   M3 (CW)
//   GPIO 13    GPIO 26
constexpr int NUM_MOTORS = 4;
constexpr int ESC_PINS[NUM_MOTORS] = {13, 32, 26, 27};

// How much each motor changes for a positive roll / pitch / yaw command.
//   roll  +  = roll right (right side down)  -> left motors speed up
//   pitch +  = nose up                        -> front motors speed up
//   yaw   +  = nose right (CW from above)     -> CCW motors speed up (their drag turns the frame CW)
struct MixRow {
  float roll, pitch, yaw;
};
constexpr MixRow MIX[NUM_MOTORS] = {
    {+1, -1, +1},  // M1 back-left,   CCW
    {-1, +1, +1},  // M2 front-right, CCW
    {-1, -1, -1},  // M3 back-right,  CW
    {+1, +1, -1},  // M4 front-left,  CW
};

// Throttle values are 0..1, mapped to 1000..2000 us (the calibrated ESC range).
constexpr int ESC_PWM_HZ = 400;  // faster than the 50 Hz bench firmware so corrections reach the motors quickly
constexpr int MIN_PULSE_US = 1000;
constexpr int MAX_PULSE_US = 2000;
constexpr float IDLE_THROTTLE = 0.17f;       // armed minimum; all four ESCs start reliably here
constexpr float MAX_THROTTLE = 0.80f;        // cap on any single motor; leaves room above hover for corrections
constexpr float THROTTLE_RISE_PER_S = 0.5f;  // limits how fast the base throttle can climb

// ---- IMU (MPU6050 on I2C) ----
constexpr int I2C_SDA = 21;
constexpr int I2C_SCL = 22;
// Body frame: x forward, y right, z down. Each body axis = sign * sensor axis[idx].
// Board mounted flat, components up, printed X arrow pointing FORWARD and Y arrow LEFT (checked by
// flying the drone): forward = +sensor X, right = -sensor Y, down = -sensor Z.
struct AxisMap {
  int idx;
  float sign;
};
constexpr AxisMap IMU_AXES[3] = {{0, +1}, {1, -1}, {2, -1}};

// ---- Control loop ----
constexpr uint32_t LOOP_HZ = 250;
constexpr float COMP_FILTER_ALPHA = 0.995f;  // trust in gyro vs accelerometer per loop (~1 s time constant)
constexpr float MANUAL_MIX_LIMIT = 0.25f;   // full stick = 25% roll/pitch motor offset
constexpr float MANUAL_YAW_LIMIT = 0.15f;   // full stick = 15% CW/CCW motor offset (spin); raise if it turns too slowly
constexpr float ARM_MAX_TILT_DEG = 15;       // refuse to arm if tilted more than this
constexpr float CRASH_ANGLE_DEG = 60;        // disarm if tilted more than this
constexpr uint32_t LINK_TIMEOUT_MS = 600;    // disarm if the phone goes quiet this long
constexpr uint32_t BENCH_MAX_MS = 30000;     // serial bench mode stops by itself after this
constexpr float THROTTLE_DEADBAND = 0.05f;   // throttle below this = motors at idle, no corrections

// ---- WiFi (the ESP32 is its own access point) ----
constexpr const char *WIFI_SSID = "esp32-drone";
constexpr const char *WIFI_PASS = "hoverhover";
