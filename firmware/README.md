# RSVP Pocket Reader — device firmware (plan)

The pocket device firmware is a **C++ port of this project's software**, not a
fork of RSVP Nano. Our reading/timing core and navigation model were built
UI-agnostic from the start precisely so they could move to hardware — this is
where that pays off. The original Python lives on the
[`main`](../../../tree/main) branch and stays the **reference spec** (its tests
validate the C++ behaves identically); the desktop app is the **book loader**.

## Target stack
- **Board:** Waveshare ESP32-S3-Touch-AMOLED-2.41
- **Toolchain:** PlatformIO + Arduino-ESP32 (or ESP-IDF)
- **Graphics:** LVGL over Waveshare's QSPI AMOLED driver (crisp large text + the
  pivot recolour; black background = pixels off = low power)
- **Input:** 3 GPIO buttons (debounced) + I²C capacitive touch → gestures
- **Peripherals:** microSD (books + settings), battery gauge, RTC, IMU

## Module mapping (Python → C++)

| Our Python | Firmware C++ | Notes |
|---|---|---|
| `core/engine.py` `RsvpEngine` | `RsvpEngine` | same pacing multipliers, sentence nav; store text in PSRAM, words as (offset,len) spans (no per-word copies) |
| `core/pivot.py` | `pivotIndex()` | identical length rule |
| `core/tokenizer.py` | `tokenize()` / spans | whitespace split → spans |
| `core/chapters.py` | (desktop only) | chapters come pre-computed in the book file |
| `core/common_words.py` | `commonWords` in flash | difficulty timing |
| `nav/` `Navigator`,`Menu`,`Button`,`Swipe` | same classes | screen stack + menu cursor, unchanged logic |
| `store.py` | `Storage` | per-book position + settings as small files on SD |
| input dispatch (`app.py` `_on_button/_on_tap/_on_swipe`) | `InputController` | buttons + tap/swipe → actions, same routing |
| `ui/app.py` rendering | `Renderer` (LVGL) | **new** — the only real rewrite |
| `books/` (EPUB/PDF) | — | **stays on the desktop**; device reads prepared text |

## Book pipeline (desktop → device)
The desktop app already parses TXT/EPUB/PDF and computes chapters. It gains an
**"Export to SD / device"** that writes, per book, a simple device format:

```
<title>\n
<chapter title>\t<word-index>  (repeated)\n
\n
<UTF-8 plain text…>
```

So the device never parses EPUB/PDF — it loads text + ready-made chapter offsets,
and our `find_chapters`/EPUB-spine logic runs once on the desktop.

## Suggested project layout
```
firmware/
  platformio.ini
  src/
    main.cpp            // setup/loop, wiring of the parts
    RsvpEngine.{h,cpp}  // port of core/engine
    pivot.{h,cpp}  tokenizer.{h,cpp}
    Navigator.{h,cpp}  Menu.{h,cpp}
    InputController.{h,cpp}  // buttons + touch → actions
    Renderer.{h,cpp}    // LVGL: reading / menu / info screens
    Storage.{h,cpp}     // SD: books + settings
    Battery.{h,cpp}     // gauge / ADC
    common_words.h
  lib/                  // Waveshare board drivers, LVGL
```

## Build order (incremental, each verifiable on the board)
1. **Bring-up:** PlatformIO project, light the AMOLED (LVGL "hello"), read the 3
   buttons + touch, mount the SD.
2. **Engine port:** `RsvpEngine` + `pivot` + `tokenizer`, validated against the
   Python tests (same inputs → same delays/words).
3. **Reading screen:** render the centred word with the pinned/coloured pivot;
   drive it from the engine + buttons (play/pause, speed).
4. **Navigation:** port `Navigator`/`Menu`; build the menu/Library/Chapters/
   Settings/Stats/About screens; touch + buttons.
5. **Storage + battery + power:** resume position/settings from SD; battery icon
   from the gauge; brightness + auto-off (AMOLED dim/off).
6. **Desktop export:** add "Export to SD" to the desktop app; close the loop.

Nothing here can be compiled/tested without the board, so this is the plan; the
port proceeds module-by-module with the Python as the spec.
