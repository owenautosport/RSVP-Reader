#include "RsvpEngine.h"
#include "common_words.h"
#include <algorithm>
#include <cctype>

// Pause multipliers (× the base per-word delay). Mirror engine.py exactly.
static constexpr double PARAGRAPH_PAUSE = 3.6;
static constexpr double SENTENCE_PAUSE  = 2.0;
static constexpr double CLAUSE_PAUSE    = 1.5;
static constexpr int    LONG_WORD_LEN   = 9;
static constexpr double LONG_WORD_PAUSE = 1.3;
static constexpr int    RARE_WORD_MINLEN = 5;
static constexpr double RARE_WORD_PAUSE = 1.2;
static constexpr double DIFFICULTY_CAP  = 1.5;

// Boundary punctuation as UTF-8 suffixes (handles multibyte … — –).
static const std::vector<std::string>& endOfSentence() {
    static const std::vector<std::string> v = {".", "!", "?", "\xE2\x80\xA6"};
    return v;
}
static const std::vector<std::string>& clauseBreak() {
    static const std::vector<std::string> v =
        {",", ";", ":", "\xE2\x80\x94", "\xE2\x80\x93"};
    return v;
}

static bool endsWith(const std::string& s, const std::string& suf) {
    return s.size() >= suf.size() &&
           s.compare(s.size() - suf.size(), suf.size(), suf) == 0;
}
static bool endsWithAny(const std::string& s, const std::vector<std::string>& sufs) {
    for (const auto& suf : sufs) if (endsWith(s, suf)) return true;
    return false;
}

RsvpEngine::RsvpEngine(std::vector<std::string> words, int wpm)
    : words_(std::move(words)), wpm_(clampWpm(wpm)) {}

void RsvpEngine::load(const std::vector<std::string>& words, int startIndex,
                      const std::unordered_set<int>& paragraphEnds) {
    words_ = words;
    int last = std::max(0, (int)words_.size() - 1);
    index_ = std::max(0, std::min(startIndex, last));
    playing_ = false;
    paragraphEnds_ = paragraphEnds;
}

double RsvpEngine::progress() const {
    if (words_.empty()) return 0.0;
    return (double)index_ / words_.size();
}

bool RsvpEngine::atEnd() const {
    return index_ >= (int)words_.size() - 1;
}

std::string RsvpEngine::currentWord() const {
    if (words_.empty()) return "";
    return words_[index_];
}

bool RsvpEngine::advance() {
    if (index_ < (int)words_.size() - 1) { index_++; return true; }
    playing_ = false;
    return false;
}

void RsvpEngine::seekTo(int i) {
    if (words_.empty()) { index_ = 0; return; }
    index_ = std::max(0, std::min(i, (int)words_.size() - 1));
}

void RsvpEngine::seekFraction(double f) {
    if (words_.empty()) return;
    f = std::max(0.0, std::min(f, 1.0));
    // round-half-to-even isn't needed here; match Python round() for our cases.
    seekTo((int)(f * (words_.size() - 1) + 0.5));
}

bool RsvpEngine::endsSentence(const std::string& w) {
    return !w.empty() && endsWithAny(w, endOfSentence());
}

int RsvpEngine::sentenceStart(int index) const {
    if (words_.empty()) return 0;
    int i = std::max(0, std::min(index, (int)words_.size() - 1));
    while (i > 0 && !endsSentence(words_[i - 1])) i--;
    return i;
}

int RsvpEngine::rewindSentence() {
    if (words_.empty()) return 0;
    int start = sentenceStart(index_);
    if (start < index_) seekTo(start);
    else if (start > 0) seekTo(sentenceStart(start - 1));
    return index_;
}

int RsvpEngine::forwardSentence() {
    if (words_.empty()) return 0;
    int i = index_, last = (int)words_.size() - 1;
    while (i < last && !endsSentence(words_[i])) i++;
    seekTo(std::min(i + 1, last));
    return index_;
}

void RsvpEngine::play() {
    if (words_.empty()) return;
    if (atEnd()) index_ = 0;
    playing_ = true;
}

bool RsvpEngine::toggle() {
    if (playing_) pause(); else play();
    return playing_;
}

int RsvpEngine::clampWpm(int v) {
    return std::max(MIN_WPM, std::min(v, MAX_WPM));
}

std::string RsvpEngine::normalize(const std::string& word) {
    static const std::string strip = ".,;:!?\"'()[]{}";
    size_t a = 0, b = word.size();
    while (a < b && strip.find(word[a]) != std::string::npos) a++;
    while (b > a && strip.find(word[b - 1]) != std::string::npos) b--;
    std::string core = word.substr(a, b - a);
    for (char& c : core) c = (char)std::tolower((unsigned char)c);
    return core;
}

double RsvpEngine::difficultyMultiplier(const std::string& word) {
    std::string core = normalize(word);
    double lengthFactor = (core.size() >= (size_t)LONG_WORD_LEN) ? LONG_WORD_PAUSE : 1.0;
    bool rare = core.size() >= (size_t)RARE_WORD_MINLEN && !commonWords().count(core);
    double rarityFactor = rare ? RARE_WORD_PAUSE : 1.0;
    double m = lengthFactor * rarityFactor;
    return m < DIFFICULTY_CAP ? m : DIFFICULTY_CAP;
}

double RsvpEngine::multiplierFor(int index) const {
    const std::string& word = words_[index];
    if (word.empty()) return 1.0;
    if (paragraphEnds_.count(index)) return PARAGRAPH_PAUSE;
    if (endsWithAny(word, endOfSentence())) return SENTENCE_PAUSE;
    if (endsWithAny(word, clauseBreak())) return CLAUSE_PAUSE;
    return difficultyMultiplier(word);
}

int RsvpEngine::delayForIndex(int index) const {
    if (index < 0 || index >= (int)words_.size()) return (int)baseDelayMs();
    return (int)(baseDelayMs() * multiplierFor(index));
}
