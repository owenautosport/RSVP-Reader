"""The RSVP engine: position, speed, play/pause, and per-word timing.

Design notes
------------
The engine is a pure state machine. It does **not** own a timer, thread, or
clock and it never sleeps. The host (the tkinter UI today) asks the engine two
things on each tick:

    * what word should be on screen now      -> ``current_word``
    * how long should it stay there          -> ``current_delay_ms``

...then schedules its own callback that far in the future and calls
``advance()``. This keeps all timing *policy* here (and unit-testable) while the
host keeps timing *mechanism* (the actual scheduling) where it belongs.

Speed is expressed in words-per-minute (WPM). The base time per word is simply
``60000 / wpm`` milliseconds; the engine then stretches that slightly for words
that end a sentence or clause so the reader gets a natural micro-pause.
"""

from __future__ import annotations

# Reasonable guard rails. The UI can expose any sub-range of this.
MIN_WPM = 60
MAX_WPM = 1200
DEFAULT_WPM = 300

# Extra lingering, as a multiple of the base per-word delay. The sentence-end
# pause is deliberately the longest: eye-tracking research shows readers spend
# extra time integrating ("wrapping up") at sentence boundaries, and a clear
# beat there helps comprehension in RSVP.
_END_OF_SENTENCE = ".!?…"
_CLAUSE_BREAK = ",;:—–"
_SENTENCE_PAUSE = 2.8  # full stop / question / exclamation
_CLAUSE_PAUSE = 1.5    # comma, semicolon, colon, dash
_LONG_WORD_LEN = 9     # words at least this long get a little more time
_LONG_WORD_PAUSE = 1.3


class RsvpEngine:
    """Stateful cursor over a list of words with speed and play/pause control."""

    def __init__(self, words: list[str] | None = None, wpm: int = DEFAULT_WPM) -> None:
        self._words: list[str] = list(words) if words else []
        self._index: int = 0
        self._playing: bool = False
        self._wpm: int = self._clamp_wpm(wpm)

    # -- content ---------------------------------------------------------

    def load(self, words: list[str], *, start_index: int = 0) -> None:
        """Replace the current text and reset position. Pauses playback."""
        self._words = list(words)
        self._index = max(0, min(start_index, max(0, len(self._words) - 1)))
        self._playing = False

    @property
    def words(self) -> list[str]:
        return self._words

    @property
    def total_words(self) -> int:
        return len(self._words)

    # -- position --------------------------------------------------------

    @property
    def index(self) -> int:
        return self._index

    @property
    def progress(self) -> float:
        """Fraction read so far in ``[0.0, 1.0]`` (0.0 when empty)."""
        if not self._words:
            return 0.0
        return self._index / len(self._words)

    @property
    def at_end(self) -> bool:
        return self._index >= len(self._words) - 1

    @property
    def current_word(self) -> str:
        """The word to display now, or ``""`` when there is no text."""
        if not self._words:
            return ""
        return self._words[self._index]

    def advance(self) -> bool:
        """Move to the next word.

        Returns ``True`` if it moved, ``False`` if already at the last word (in
        which case playback is stopped).
        """
        if self._index < len(self._words) - 1:
            self._index += 1
            return True
        self._playing = False
        return False

    def seek_to(self, index: int) -> None:
        if not self._words:
            self._index = 0
            return
        self._index = max(0, min(index, len(self._words) - 1))

    def seek_fraction(self, fraction: float) -> None:
        """Jump to a position given as a fraction in ``[0.0, 1.0]``."""
        if not self._words:
            return
        fraction = max(0.0, min(fraction, 1.0))
        self.seek_to(round(fraction * (len(self._words) - 1)))

    def restart(self) -> None:
        self._index = 0

    # -- sentence navigation (rewind / skip) ----------------------------
    #
    # RSVP removes the reader's ability to glance back and re-read; the
    # comprehension research is clear that those regressions matter. These let a
    # host give that ability back at sentence granularity.

    @staticmethod
    def _ends_sentence(word: str) -> bool:
        return bool(word) and word[-1] in _END_OF_SENTENCE

    def sentence_start(self, index: int) -> int:
        """Index of the first word of the sentence containing ``index``."""
        i = max(0, min(index, len(self._words) - 1))
        while i > 0 and not self._ends_sentence(self._words[i - 1]):
            i -= 1
        return i

    def rewind_sentence(self) -> int:
        """Jump to the start of the current sentence, or the previous one if
        already there. Returns the new index. Re-read what you just missed."""
        if not self._words:
            return 0
        start = self.sentence_start(self._index)
        if start < self._index:
            self.seek_to(start)            # back to the start of this sentence
        elif start > 0:
            self.seek_to(self.sentence_start(start - 1))  # the sentence before
        return self._index

    def forward_sentence(self) -> int:
        """Jump to the start of the next sentence. Returns the new index."""
        if not self._words:
            return 0
        i = self._index
        last = len(self._words) - 1
        while i < last and not self._ends_sentence(self._words[i]):
            i += 1
        self.seek_to(min(i + 1, last))
        return self._index

    # -- playback state --------------------------------------------------

    @property
    def is_playing(self) -> bool:
        return self._playing

    def play(self) -> None:
        if not self._words:
            return
        # Starting from the very end rewinds so there is something to read.
        if self.at_end:
            self._index = 0
        self._playing = True

    def pause(self) -> None:
        self._playing = False

    def toggle(self) -> bool:
        """Flip play/pause. Returns the new ``is_playing`` value."""
        if self._playing:
            self.pause()
        else:
            self.play()
        return self._playing

    # -- speed -----------------------------------------------------------

    @property
    def wpm(self) -> int:
        return self._wpm

    @wpm.setter
    def wpm(self, value: int) -> None:
        self._wpm = self._clamp_wpm(value)

    def adjust_wpm(self, delta: int) -> int:
        """Nudge speed by ``delta`` WPM (clamped). Returns the new WPM."""
        self.wpm = self._wpm + delta
        return self._wpm

    @staticmethod
    def _clamp_wpm(value: int) -> int:
        return max(MIN_WPM, min(int(value), MAX_WPM))

    # -- timing ----------------------------------------------------------

    @property
    def base_delay_ms(self) -> float:
        """Milliseconds per word from raw WPM, before any lingering."""
        return 60_000.0 / self._wpm

    @property
    def current_delay_ms(self) -> int:
        """How long the current word should stay on screen, in milliseconds."""
        return self._delay_for(self.current_word)

    def _delay_for(self, word: str) -> int:
        base = self.base_delay_ms
        multiplier = 1.0
        if word:
            last = word[-1]
            if last in _END_OF_SENTENCE:
                multiplier = _SENTENCE_PAUSE
            elif last in _CLAUSE_BREAK:
                multiplier = _CLAUSE_PAUSE
            elif len(word) >= _LONG_WORD_LEN:
                multiplier = _LONG_WORD_PAUSE
        return int(base * multiplier)
