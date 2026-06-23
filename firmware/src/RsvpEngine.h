// The RSVP engine: position, speed, play/pause, per-word timing.
// Port of rsvp/core/engine.py. Pure logic — no Arduino/hardware deps, so it
// compiles on the host (g++) for verification and on the ESP32 unchanged.
#pragma once
#include <string>
#include <vector>
#include <unordered_set>

class RsvpEngine {
public:
    static constexpr int MIN_WPM = 60;
    static constexpr int MAX_WPM = 1200;
    static constexpr int DEFAULT_WPM = 300;

    RsvpEngine(std::vector<std::string> words = {}, int wpm = DEFAULT_WPM);

    // -- content --
    void load(const std::vector<std::string>& words, int startIndex = 0,
              const std::unordered_set<int>& paragraphEnds = {});
    int totalWords() const { return (int)words_.size(); }
    const std::vector<std::string>& words() const { return words_; }

    // -- position --
    int index() const { return index_; }
    double progress() const;
    bool atEnd() const;
    std::string currentWord() const;
    bool advance();
    void seekTo(int i);
    void seekFraction(double f);
    void restart() { index_ = 0; }

    // -- sentence navigation --
    int sentenceStart(int index) const;
    int rewindSentence();
    int forwardSentence();

    // -- playback --
    bool isPlaying() const { return playing_; }
    void play();
    void pause() { playing_ = false; }
    bool toggle();

    // -- speed --
    int wpm() const { return wpm_; }
    void setWpm(int v) { wpm_ = clampWpm(v); }
    int adjustWpm(int delta) { setWpm(wpm_ + delta); return wpm_; }

    // -- timing --
    double baseDelayMs() const { return 60000.0 / wpm_; }
    int currentDelayMs() const { return delayForIndex(index_); }

private:
    std::vector<std::string> words_;
    int index_ = 0;
    bool playing_ = false;
    int wpm_;
    std::unordered_set<int> paragraphEnds_;

    int delayForIndex(int index) const;
    double multiplierFor(int index) const;

    static int clampWpm(int v);
    static bool endsSentence(const std::string& w);
    static double difficultyMultiplier(const std::string& word);
    static std::string normalize(const std::string& word);
};
