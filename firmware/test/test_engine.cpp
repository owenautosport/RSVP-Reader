// Host-side verification: the C++ engine must produce the SAME results as the
// Python (rsvp/core). Expected values were captured by running the Python engine.
//   build:  g++ -std=c++17 firmware/test/test_engine.cpp firmware/src/RsvpEngine.cpp -o /tmp/te
#include "../src/RsvpEngine.h"
#include "../src/pivot.h"
#include "../src/tokenizer.h"
#include <cstdio>

static int failures = 0;
#define CHECK(cond) do { if(!(cond)){ printf("FAIL line %d: %s\n", __LINE__, #cond); failures++; } } while(0)
#define EQ(a,b) do { long _a=(long)(a), _b=(long)(b); if(_a!=_b){ \
    printf("FAIL line %d: %s == %s  (got %ld, want %ld)\n", __LINE__, #a, #b, _a, _b); failures++; } } while(0)

int main() {
    // pivot
    EQ(pivotIndex(""), 0);  EQ(pivotIndex("a"), 0);   EQ(pivotIndex("to"), 1);
    EQ(pivotIndex("the"), 1); EQ(pivotIndex("reader"), 2); EQ(pivotIndex("wonderfully"), 3);
    EQ(pivotIndex("extraordinarily"), 4); EQ(pivotIndex("people"), 2);
    EQ(pivotIndex("comfortable"), 3); EQ(pivotIndex("cat"), 1);

    // base delay + a full per-word delay table @300 wpm
    RsvpEngine e(tokenize("Hello world. Next clause, here longword wonderfully end."), 300);
    CHECK(e.baseDelayMs() == 200.0);
    const char* w[]    = {"Hello","world.","Next","clause,","here","longword","wonderfully","end."};
    int         exp[]  = { 240,    400,     200,   300,      200,   240,       300,          400 };
    for (int i = 0; i < 8; i++) { e.seekTo(i); CHECK(e.currentWord() == w[i]); EQ(e.currentDelayMs(), exp[i]); }

    // difficulty on single words
    auto diff = [&](const char* word) { e.load(tokenize(word)); return e.currentDelayMs(); };
    EQ(diff("the"), 200); EQ(diff("cat"), 200); EQ(diff("people"), 200);
    EQ(diff("comfortable"), 300); EQ(diff("wonderfully"), 300); EQ(diff("reading"), 200);

    // sentence navigation
    e.load(tokenize("One two three. Four five six! Seven eight nine ten."));
    EQ(e.sentenceStart(5), 3); EQ(e.sentenceStart(1), 0); EQ(e.sentenceStart(7), 6);
    e.seekTo(5); EQ(e.rewindSentence(), 3); EQ(e.rewindSentence(), 0); EQ(e.rewindSentence(), 0);
    e.seekTo(1); EQ(e.forwardSentence(), 3);
    e.seekTo(4); EQ(e.forwardSentence(), 6);
    e.seekTo(7); EQ(e.forwardSentence(), 9);

    // paragraph pause (3.6x)
    e.load(tokenize("A end. B next."), 0, {1}); e.seekTo(1); EQ(e.currentDelayMs(), 720);

    // play/pause, wpm clamp, advance stops at end
    e.load({"a", "b"}); EQ((int)e.toggle(), 1); EQ((int)e.toggle(), 0);
    e.setWpm(99999); EQ(e.wpm(), 1200); e.setWpm(1); EQ(e.wpm(), 60);
    e.load({"a", "b"}); e.play(); CHECK(e.advance()); CHECK(!e.advance()); CHECK(!e.isPlaying());

    if (failures == 0) printf("ALL C++ ENGINE TESTS PASS (matches Python)\n");
    else printf("%d FAILURE(S)\n", failures);
    return failures ? 1 : 0;
}
