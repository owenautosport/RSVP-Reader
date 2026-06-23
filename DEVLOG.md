# RSVP Pocket E-Reader — development log

A written history of how this project was built, the decisions made, and why.
It is a **summary of the build sessions**, not a verbatim chat transcript — but
it captures the full arc so you (or anyone) can pick up where we left off.

The project has two halves, split across branches:
- **`main`** — the desktop app (Windows / macOS / Linux), released as **v1.0.0**.
- **`device`** — the pocket hardware + the device firmware (a C++ port of the
  desktop reading engine), plus the BOM, order list, and 3D-printed case.

---

## 1. The goal

A minimal, quiet, fully-offline RSVP speed reader (one word at a time, centered,
at a chosen speed). Modeled on the open-source **RSVP Nano** pocket device — this
project began as its **desktop counterpart**. Hard constraints from day one:
reading is the whole experience; fully offline; and **keep the reading/timing
core separate from the UI/input** so it can move to hardware later. (That last
decision is what made the eventual firmware port cheap.)

## 2. Stack choice

**Python 3 + tkinter.** Reason: tkinter ships with Python → zero third-party
dependencies → offline by construction, while a dependency-free core engine stays
portable. (PDF later added one optional dep, `pypdf`.)

## 3. Desktop app — the feature arc (branch `main`)

Built incrementally, each step verified, committed, and pushed:

1. **MVP** — open a book, show one word at a time, adjustable WPM, play/pause.
   Architecture set: `core/` (UI-agnostic engine + tokenizer), `ui/` (tkinter).
2. **ORP pivot** — highlight + pin the optimal-recognition-point letter so the
   eye never drifts (`core/pivot.py`, fixed pivot column).
3. **Peripheral context words** — tried, then **reverted** (user found it
   distracting). Good example of the build-it/try-it/revert loop.
4. **Read-normally view** (`tab`) — show the whole book as a paragraph with the
   current word highlighted; click any word to resume there. Needed
   `token_spans()` to map screen position ↔ word index.
5. **Reading research** — two deep-research passes (speed, comprehension) were
   started, then **stopped early to save usage**; ~147 source-attributed claims
   were harvested from disk and synthesized. Key findings drove the next steps:
   regressions/re-reading matter for comprehension; comprehension is fine up to
   ~350 wpm then drops; word length + frequency independently affect fixation.
6. **Sentence rewind, longer sentence pauses, switchable fonts.** The longer
   sentence pause was then **reverted** (interrupted flow) — kept the rewind.
7. **Tier-2 timing** — difficulty-aware per-word delay (longer for long /
   less-common words via a small bundled common-word list) + paragraph-end
   pauses (`core/common_words.py`, `paragraph_end_indices`).
8. **Menu system + device input model.** Decided the device would have **3 top
   buttons + a touchscreen**; built a toolkit-agnostic `nav/` layer (Button/Swipe
   input, Menu, Navigator screen-stack) so the same logic maps to Mac keys+mouse
   now and the device later. Screens: Reading, Library, Chapters, Settings,
   Stats, About.
9. **Save your place** (`store.py`) — per-book position + settings, autosaved
   while reading; resume to the **furthest** point reached (re-reading never
   lowers it).
10. **Library** (add/remove books), **Chapters/progress** (real headings or
    %-markers, "you are here"), **Settings** (speed/font/pivot/brightness/
    low-power/auto-off/battery), **Stats** (progress + time read), **About**.
11. **iPhone-style battery indicator** (accent-orange), brightness (window
    opacity stand-in), **low-power mode**, **auto-off** sleep timer.
12. **EPUB** support — zero-dependency (`zipfile` + `xml.etree` + `html.parser`),
    real chapters from the spine. **PDF** support — optional `pypdf`, chapters
    from the outline.
13. **Polish** — list scrolling, EPUB/PDF metadata titles in the Library, a
    fixed Library-render bug, and a single **onboarding sample** that explains
    RSVP + the controls.
14. **v1.0.0 release** — cross-platform installers built by **GitHub Actions**
    (Windows Inno-Setup `.exe`, macOS `.dmg`, Linux `.AppImage`) and published to
    the GitHub Release on a `vX.Y.Z` tag. Code made cross-platform (per-OS
    battery, fonts, bundle-aware paths).

Notable reverts (kept honest): peripheral context words, and the long
sentence-end pause.

## 4. Hardware planning (branch `device`)

The path to the parts list, with the reasoning that shaped it:

- **Display must be fast-refresh (LCD/OLED), not e-ink** — RSVP flips a word
  every ~100–250 ms; e-paper can't keep up.
- **Form factor** — chosen to match the **Canon EOS 90D flip screen** footprint
  (3.0″, 3:2, ~64×43 mm active; device ≈ ~58 mm wide). "Phone-sized defeats the
  purpose."
- **Compute** — investigated Pi Zero (runs our Python, but bigger device, and
  the Zero has no DSI) vs ESP32. Looked at **RSVP Nano's** own hardware:
  integrated **Waveshare ESP32-S3 Touch** boards. That revealed small
  **AMOLED-with-touch** exists only as these integrated ESP32 boards (a true 3–4″
  AMOLED HDMI/DSI touch panel isn't a buyable part).
- **Decision** — go **ESP32-S3** (tiny, true-black AMOLED, great battery, custom
  case), accepting that the device runs **firmware**, not our Python — which fits
  the original "desktop counterpart" framing. Specifically the **Waveshare
  ESP32-S3-Touch-AMOLED-2.41** (2.41″ 600×450 AMOLED, cap touch, USB-C, microSD,
  LiPo charging, IMU, RTC, 34-pin GPIO).
- **Rest of the BOM** — ~1000 mAh LiPo (⚠ MX1.25 connector + polarity caveat),
  3 tactile buttons + printed caps, 16 GB microSD, custom 3D case. ~$60–70.
  Chosen products recorded in `hardware/ORDER.md` (UK sources).

## 5. Device firmware (branch `device`)

- **Decision: a C++ port of *our* software**, not a fork of RSVP Nano and not
  MicroPython. C++ because Waveshare's drivers for this board exist in C++
  (proven by RSVP Nano), better battery, no GC pauses. The clean core/nav split
  made the port cheap; the Python is the **reference spec**.
- **Done + host-verified (compiled with g++ on the Mac, matching the Python):**
  - `RsvpEngine` + `pivot` + `tokenizer` (`firmware/test/test_engine.cpp`)
  - `Navigator` + `Menu` + `actions` (`firmware/test/test_nav.cpp`)
  - `Renderer.h` — the abstract display boundary (LVGL impl on-device)
- **Book pipeline** — the desktop app's `rsvp/export.py` ("Export to SD")
  converts TXT/EPUB/PDF into a simple `.rsvp` file (text + chapter word-indices)
  so the firmware never parses EPUB/PDF.
- **Remaining (needs the board):** PlatformIO bring-up, the LVGL renderer +
  Waveshare driver, the input controller, and SD/battery/power wiring.

## 6. Repo layout

```
main    → desktop app: rsvp/ (core, nav, books, ui, store, export), packaging/,
          .github release CI, samples/. Released v1.0.0.
device  → hardware/ (README BOM, ORDER.md, case.scad) + firmware/ (C++ engine +
          nav ports, Renderer.h, plan, platformio.ini). Device-only.
```

## 7. Where to pick up

1. Order the parts (`hardware/ORDER.md`).
2. When the board arrives → measure it → update `case.scad` → print.
3. Finish the firmware's hardware layer (LVGL renderer + input + SD/battery),
   using the verified C++ core + the Python tests as the spec.
4. Use `python -m rsvp.export <book> <sd>` to load books onto the device.

---

*Generated as a development summary at the end of the build sessions. For the
exact code and commit history, see the git log on `main` and `device`.*
