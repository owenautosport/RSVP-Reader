// Split book text into display words. Port of rsvp/core/tokenizer.py.
// Whitespace-separated, like Python str.split(): collapses runs, ignores
// leading/trailing whitespace, keeps punctuation attached to each word.
#pragma once
#include <string>
#include <vector>

inline std::vector<std::string> tokenize(const std::string& text) {
    std::vector<std::string> words;
    size_t i = 0, n = text.size();
    while (i < n) {
        // skip whitespace (ASCII; UTF-8 continuation bytes are high-bit, not ws)
        while (i < n && (unsigned char)text[i] <= ' ') i++;
        size_t start = i;
        while (i < n && (unsigned char)text[i] > ' ') i++;
        if (i > start) words.push_back(text.substr(start, i - start));
    }
    return words;
}
