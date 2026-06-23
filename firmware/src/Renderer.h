// The display surface the firmware draws to.
//
// Kept abstract so all the logic above it (RsvpEngine, Navigator/Menu, the input
// controller) stays hardware-free and host-testable — exactly like the desktop
// app's tkinter layer was separate from the core. The on-device implementation
// fulfils this with LVGL + the Waveshare AMOLED (QSPI) driver; a host stub could
// fulfil it for off-device UI tests later.
#pragma once
#include <string>
#include <vector>

class Menu;

class Renderer {
public:
    virtual ~Renderer() = default;

    // Reading screen: the centred word with its pivot letter pinned/highlighted.
    virtual void drawWord(const std::string& word, int pivotIndex) = 0;

    // A list screen (menu / library / chapters / settings) with the cursor.
    virtual void drawMenu(const Menu& menu) = 0;

    // An info screen (stats / about): a title and plain lines.
    virtual void drawInfo(const std::string& title,
                          const std::vector<std::string>& lines) = 0;

    // Power / display.
    virtual void setBrightness(int percent) = 0;  // backlight / AMOLED dim level
    virtual void sleep() = 0;                      // auto-off: display off
    virtual void wake() = 0;
};
