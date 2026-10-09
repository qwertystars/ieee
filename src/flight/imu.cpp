#include "imu.h"

#include <Wire.h>

#include "config.h"

namespace {
constexpr uint8_t ADDR = 0x68;
constexpr float GYRO_LSB_PER_DPS = 65.5f;   // +-500 deg/s range
constexpr float ACCEL_LSB_PER_G = 4096.0f;  // +-8 g range
constexpr float STILL_MAX_SPREAD_DPS = 4.0f;

bool writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

bool readRegs(uint8_t reg, uint8_t *buf, size_t len) {
  Wire.beginTransmission(ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(ADDR, (uint8_t)len) != len) return false;
  for (size_t i = 0; i < len; i++) buf[i] = Wire.read();
  return true;
}
}  // namespace

bool Mpu6050::begin() {
  Wire.begin(I2C_SDA, I2C_SCL, 400000);
  Wire.setTimeOut(5);
  if (!readRegs(0x75, &whoAmI_, 1)) return false;  // WHO_AM_I: 0x68 on genuine parts, clones vary
  if (!writeReg(0x6B, 0x80)) return false;         // reset
  delay(100);
  return writeReg(0x6B, 0x01)     // wake, clock from gyro PLL
         && writeReg(0x19, 0x00)  // sample rate divider: 1 kHz
         && writeReg(0x1A, 0x03)  // low-pass ~44 Hz: cuts motor vibration
         && writeReg(0x1B, 0x08)  // gyro +-500 deg/s
         && writeReg(0x1C, 0x10); // accel +-8 g
}

bool Mpu6050::readSensorFrame(float gyro[3], float accel[3]) {
  uint8_t b[14];
  if (!readRegs(0x3B, b, sizeof b)) return false;
  auto be16 = [&](int i) { return (int16_t)((b[i] << 8) | b[i + 1]); };
  float a[3], g[3];
  for (int i = 0; i < 3; i++) {
    a[i] = be16(i * 2) / ACCEL_LSB_PER_G;
    g[i] = be16(8 + i * 2) / GYRO_LSB_PER_DPS;  // bytes 6-7 are temperature
  }
  for (int i = 0; i < 3; i++) {
    accel[i] = IMU_AXES[i].sign * a[IMU_AXES[i].idx];
    gyro[i] = IMU_AXES[i].sign * g[IMU_AXES[i].idx];
  }
  return true;
}

bool Mpu6050::read(ImuSample &out) {
  if (!readSensorFrame(out.gyro, out.accel)) return false;
  for (int i = 0; i < 3; i++) out.gyro[i] -= gyroBias_[i];
  return true;
}

bool Mpu6050::calibrateGyro(int samples) {
  float sum[3] = {}, lo[3], hi[3];
  for (int i = 0; i < 3; i++) {
    lo[i] = 1e9f;
    hi[i] = -1e9f;
  }
  for (int n = 0; n < samples; n++) {
    float g[3], a[3];
    if (!readSensorFrame(g, a)) return false;
    for (int i = 0; i < 3; i++) {
      sum[i] += g[i];
      lo[i] = min(lo[i], g[i]);
      hi[i] = max(hi[i], g[i]);
    }
    delay(2);
  }
  for (int i = 0; i < 3; i++) {
    if (hi[i] - lo[i] > STILL_MAX_SPREAD_DPS) return false;
  }
  for (int i = 0; i < 3; i++) gyroBias_[i] = sum[i] / samples;
  return true;
}
