#include "Menu.h"

void Menu::reset() {
    index_ = 0;
    if (!items_.empty() && !items_[0].enabled) move(1);
}

void Menu::move(int delta) {
    if (items_.empty()) return;
    int step = delta > 0 ? 1 : -1;
    int steps = delta > 0 ? delta : -delta;
    int n = (int)items_.size();
    int i = index_;
    for (int k = 0; k < steps; k++) {
        int j = i;
        while (j + step >= 0 && j + step < n) {
            j += step;
            if (items_[j].enabled) { i = j; break; }
        }
    }
    index_ = i;
}

void Menu::selectIndex(int index) {
    if (index >= 0 && index < (int)items_.size() && items_[index].enabled)
        index_ = index;
}
