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

from .common_words import COMMON_WORDS

# Reasonable guard rails. The UI can expose any sub-range of this.
MIN_WPM = 60
MAX_WPM = 1200
DEFAULT_WPM = 300

# Extra lingering, as a multiple of the base per-word delay. The pauses at
# paragraph and sentence boundaries are the longest: eye-tracking research shows
# readers spend extra time integrating ("wrapping up") at those points, and a
# clear beat there helps comprehension in RSVP.
_END_OF_SENTENCE = ".!?…"
_CLAUSE_BREAK = ",;:—–"
_PARAGRAPH_PAUSE = 3.6  # extra breath at the end of a paragraph
_SENTENCE_PAUSE = 2.8   # full stop / question / exclamation
_CLAUSE_PAUSE = 1.5     # comma, semicolon, colon, dash

# Per-word difficulty (applied to words without boundary punctuation). Length
# and familiarity are independent signals in the reading literature; longer and
# less common words get a touch more time, combined but capped.
_LONG_WORD_LEN = 9      # characters; at/above this counts as a "long" word
_LONG_WORD_PAUSE = 1.3
_RARE_WORD_MINLEN = 5   # don't penalise short words even if uncommon
_RARE_WORD_PAUSE = 1.2  # word not in the common-word set
_DIFFICULTY_CAP = 1.5   # ceiling for the combined length×rarity factor


def _normalize(word: str) -> str:
    """Lowercase a word and strip surrounding punctuation for lookup."""
    return word.strip(".,;:!?…—–\"'()[]{}«»“”‘’").lower()


class RsvpEngine:
    """Stateful cursor over a list of words with speed and play/pause control."""

    def __init__(self, words: list[str] | None = None, wpm: int = DEFAULT_WPM) -> None:
        self._words: list[str] = list(words) if words else []
        self._index: int = 0
        self._playing: bool = False
        self._wpm: int = self._clamp_wpm(wpm)
        self._paragraph_ends: frozenset[int] = frozenset()

    # -- content ---------------------------------------------------------

    def load(
        self,
        words: list[str],
        *,
        start_index: int = 0,
        paragraph_ends: frozenset[int] | set[int] | None = None,
    ) -> None:
        """Replace the current text and reset position. Pauses playback.

        ``paragraph_ends`` is an optional set of word indices that fall at the
        end of a paragraph; the engine adds a longer pause after each so the
        reader gets a breath between paragraphs.
        """
        self._words = list(words)
        self._index = max(0, min(start_index, max(0, len(self._words) - 1)))
        self._playing = False
        self._paragraph_ends = frozenset(paragraph_ends or ())

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
        return self._delay_for_index(self._index)

    def _delay_for_index(self, index: int) -> int:
        if not (0 <= index < len(self._words)):
            return int(self.base_delay_ms)
        return int(self.base_delay_ms * self._multiplier_for(index))

    def _multiplier_for(self, index: int) -> float:
        """Boundary pauses dominate; otherwise scale by word difficulty.

        Precedence: paragraph end > sentence end > clause break > difficulty
        (length and familiarity). Boundaries are about giving the reader a beat
        to integrate; difficulty is about the word itself, so only one applies.
        """
        word = self._words[index]
        if not word:
            return 1.0
        if index in self._paragraph_ends:
            return _PARAGRAPH_PAUSE
        last = word[-1]
        if last in _END_OF_SENTENCE:
            return _SENTENCE_PAUSE
        if last in _CLAUSE_BREAK:
            return _CLAUSE_PAUSE
        return self._difficulty_multiplier(word)

    @staticmethod
    def _difficulty_multiplier(word: str) -> float:
        core = _normalize(word)
        length_factor = _LONG_WORD_PAUSE if len(core) >= _LONG_WORD_LEN else 1.0
        rare = len(core) >= _RARE_WORD_MINLEN and core not in COMMON_WORDS
        rarity_factor = _RARE_WORD_PAUSE if rare else 1.0
        return min(length_factor * rarity_factor, _DIFFICULTY_CAP)
