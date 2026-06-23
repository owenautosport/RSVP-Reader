"""Compare version strings (semantic-version-ish) so the app can tell whether a
GitHub release is genuinely newer than what's running.

Release tags look like ``v1.2.3`` or ``1.2.3-beta``; ``rsvp.__version__`` looks
like ``1.0.0``. We parse both into a comparable shape and follow the one semver
rule that matters here: a final release outranks its own pre-release
(``1.0.0`` > ``1.0.0-beta``).
"""

from __future__ import annotations


def parse_version(s: str) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Parse a version string into ``(release_numbers, prerelease_parts)``.

    ``"v1.2.3"`` -> ``((1, 2, 3), ())``; ``"1.0.0-beta"`` -> ``((1, 0, 0),
    ("beta",))``. Non-numeric junk in a release segment degrades to 0 rather
    than raising, so a malformed remote tag simply compares as old.
    """
    s = s.strip().lstrip("vV")
    pre: tuple[str, ...] = ()
    if "-" in s:
        s, _, p = s.partition("-")
        pre = tuple(part for part in p.split(".") if part)
    numbers: list[int] = []
    for chunk in s.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        numbers.append(int(digits) if digits else 0)
    return tuple(numbers), pre


def is_newer(current: str, candidate: str) -> bool:
    """True if ``candidate`` is a strictly newer version than ``current``."""
    try:
        cur_rel, cur_pre = parse_version(current)
        cand_rel, cand_pre = parse_version(candidate)
    except Exception:
        return False

    width = max(len(cur_rel), len(cand_rel))
    cur_rel += (0,) * (width - len(cur_rel))
    cand_rel += (0,) * (width - len(cand_rel))
    if cand_rel != cur_rel:
        return cand_rel > cur_rel

    # Same release numbers: a final release (no pre-release) beats a pre-release.
    cur_final = cur_pre == ()
    cand_final = cand_pre == ()
    if cand_final != cur_final:
        return cand_final
    if cand_final:  # both final and equal release numbers
        return False
    return cand_pre > cur_pre  # both pre-releases: lexicographic
