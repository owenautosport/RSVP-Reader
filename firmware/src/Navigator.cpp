#include "Navigator.h"

Menu* Navigator::menu() {
    auto it = menus_.find(screen());
    return it == menus_.end() ? nullptr : &it->second;
}

void Navigator::open(Screen s) {
    auto it = menus_.find(s);
    if (it == menus_.end()) return;
    it->second.reset();
    if (screen() != s) stack_.push_back(s);
}

void Navigator::open(Screen s, std::vector<MenuItem> items) {
    auto it = menus_.find(s);
    if (it == menus_.end()) return;
    it->second.setItems(std::move(items));
    it->second.reset();
    if (screen() != s) stack_.push_back(s);
}

void Navigator::back() {
    if (stack_.size() > 1) stack_.pop_back();
}

void Navigator::goReading() {
    stack_.clear();
    stack_.push_back(Screen::Reading);
}

void Navigator::move(int delta) {
    if (Menu* m = menu()) m->move(delta);
}

std::string Navigator::select() {
    Menu* m = menu();
    if (!m) return "";
    const MenuItem* c = m->current();
    return (c && c->enabled) ? c->id : "";
}
