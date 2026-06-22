"""A small set of the most frequent English words, used as a rough familiarity
signal for per-word timing.

Eye-tracking research finds that low-frequency (less familiar) words get longer
fixations than common ones, independent of word length. A full frequency corpus
would be heavier and online; for a tiny offline reader, membership in this
common-word set is a good enough proxy: a normalized word in the set is treated
as familiar (no slow-down), anything else as relatively unfamiliar.

This is data only — no logic. The engine decides what to do with it.
"""

from __future__ import annotations

# ~450 of the most common English words (function words plus very high-frequency
# content words). Lowercase, no punctuation. Order is irrelevant; it becomes a
# frozenset for O(1) lookup.
_WORDS = """
the be to of and a in that have i it for not on with he as you do at this but his
by from they we say her she or an will my one all would there their what so up out
if about who get which go me when make can like time no just him know take people
into year your good some could them see other than then now look only come its over
think also back after use two how our work first well way even new want because any
these give day most us is are was were been has had did said get got make made go
went come came know knew take took see saw look looked use used find found give gave
tell told ask asked work worked seem seemed feel felt try tried leave left call
called man woman child world life hand part eye place week case point government
company number group problem fact be been being am more very much many such own same
those each few while where why before through between under again against here once
something nothing everything someone anyone everyone always never often sometimes
usually really almost together perhaps however therefore though although yet still
around enough quite rather across behind beyond during without within along among
big small large great little long short high low old young right left next last
early late hard easy true false open close full empty happy sad good bad better best
read reading word words book books page text speed slow fast quick light dark
house home room door car water food money mother father friend night morning day
head face hand foot heart mind voice name story word line side end top bottom front
turn move walk run sit stand keep let put set bring begin start stop hold show hear
play feel seem become leave meet learn change live believe happen include continue
write speak grow open walk win lose pay send build spend talk carry break wait wear
""".split()

COMMON_WORDS: frozenset[str] = frozenset(_WORDS)
