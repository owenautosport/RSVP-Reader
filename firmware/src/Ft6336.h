// Minimal FT6336 capacitive touch driver (I2C) for the LCDwiki 2.8" board.
// Reads a single touch point in the panel's native (portrait) coordinates.
#pragma once
#include <Arduino.h>
#include <Wire.h>

class Ft6336 {
public:
    Ft6336(uint8_t sda, uint8_t scl, int8_t rst = -1, uint8_t addr = 0x38)
        : sda_(sda), scl_(scl), rst_(rst), addr_(addr) {}

    void begin() {
        if (rst_ >= 0) {
            pinMode(rst_, OUTPUT);
            digitalWrite(rst_, LOW);  delay(10);
            digitalWrite(rst_, HIGH); delay(300);
        }
        Wire.begin(sda_, scl_);
        Wire.setClock(400000);
    }

    // Returns true if a finger is down; x,y are panel-native (portrait) coords.
    bool readRaw(uint16_t &x, uint16_t &y) {
        Wire.beginTransmission(addr_);
        Wire.write(0x02);                       // TD_STATUS register
        if (Wire.endTransmission(false) != 0) return false;
        if (Wire.requestFrom((int)addr_, 5) != 5) return false;
        uint8_t td = Wire.read();
        uint8_t xh = Wire.read(), xl = Wire.read();
        uint8_t yh = Wire.read(), yl = Wire.read();
        if ((td & 0x0F) == 0) return false;     // no touch points
        x = (uint16_t)((xh & 0x0F) << 8) | xl;
        y = (uint16_t)((yh & 0x0F) << 8) | yl;
        return true;
    }

private:
    uint8_t sda_, scl_, addr_;
    int8_t rst_;
};
