// Optimal Recognition Point — the pivot letter to anchor a word on.
// Port of rsvp/core/pivot.py. Length-based rule (Spritz/RSVP-Nano style).
#pragma once
#include <string>

inline int pivotIndex(const std::string& word) {
    // NOTE: byte length; matches Python len() for ASCII words.
    size_t n = word.size();
    if (n <= 1) return 0;
    if (n <= 5) return 1;
    if (n <= 9) return 2;
    if (n <= 13) return 3;
    return 4;
}
