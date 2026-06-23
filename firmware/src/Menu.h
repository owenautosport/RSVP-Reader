// Vertical-list menu model — port of rsvp/nav/menu.py.
// Items + a selection cursor that skips disabled rows. Pure data/cursor logic.
#pragma once
#include <string>
#include <vector>

struct MenuItem {
    std::string id;       // stable intent id the app acts on
    std::string label;    // what the user sees
    bool enabled;         // dimmed / not selectable when false
    MenuItem(std::string id_, std::string label_, bool enabled_ = true)
        : id(std::move(id_)), label(std::move(label_)), enabled(enabled_) {}
};

class Menu {
public:
    Menu(std::vector<MenuItem> items = {}) : items_(std::move(items)) {}

    const std::vector<MenuItem>& items() const { return items_; }
    void setItems(std::vector<MenuItem> items) { items_ = std::move(items); index_ = 0; }
    int index() const { return index_; }
    const MenuItem* current() const { return items_.empty() ? nullptr : &items_[index_]; }

    void reset();                 // cursor to the first selectable item
    void move(int delta);         // move, skipping disabled, clamped
    void selectIndex(int index);  // point at index if it exists and is enabled

private:
    std::vector<MenuItem> items_;
    int index_ = 0;
};
