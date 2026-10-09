#pragma once
#include <Arduino.h>

// One reading in the body frame (x forward, y right, z down).
struct ImuSample {
  float gyro[3];   // deg/s, gyro bias removed
  float accel[3];  // g; level and still reads about (0, 0, -1)
};

class Mpu6050 {
 public:
  // Starts I2C and configures the sensor. Returns false if it doesn't answer.
  bool begin();
  bool read(ImuSample &out);
  // Averages the gyro while the drone sits still. Returns false if it moved.
  bool calibrateGyro(int samples);
  uint8_t whoAmI() const { return whoAmI_; }

 private:
  bool readSensorFrame(float gyro[3], float accel[3]);
  float gyroBias_[3] = {};
  uint8_t whoAmI_ = 0;
};
