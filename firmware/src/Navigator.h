// Screen state machine — port of rsvp/nav/navigator.py.
// A stack of screens (READING is the base); list screens are pushed and popped.
// Returns a selected item's id; the app acts on it.
#pragma once
#include <map>
#include <string>
#include <vector>
#include "Menu.h"

enum class Screen { Reading, Menu, Library, Chapters, Settings, Stats, About };

class Navigator {
public:
    Navigator(std::map<Screen, Menu> menus) : menus_(std::move(menus)) {
        stack_.push_back(Screen::Reading);
    }

    Screen screen() const { return stack_.back(); }
    bool inMenu() const { return screen() != Screen::Reading; }
    Menu* menu();                              // current screen's menu, or nullptr

    void open(Screen screen);                  // push (refresh in place if already there)
    void open(Screen screen, std::vector<MenuItem> items);  // ...replacing its items
    void back();                               // pop one screen
    void goReading();                          // collapse to reading
    void move(int delta);
    std::string select();                      // highlighted item id, or "" if none/disabled

private:
    std::map<Screen, Menu> menus_;
    std::vector<Screen> stack_;
};
