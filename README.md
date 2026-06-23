# RSVP Pocket E-Reader — device

The handheld pocket reader: one word at a time (RSVP), true-black AMOLED,
3 buttons + touch, fully offline.

> **This branch holds the device only** — the hardware design and the firmware.
> The cross-platform **desktop app** (the reader for your PC, and the tool that
> loads books onto the device) lives on the [`main`](../../tree/main) branch.

## What's here
- **[`hardware/`](hardware/)** — the bill of materials and a parametric
  3D-printed case (`case.scad`).
- **[`firmware/`](firmware/)** — the device firmware: a **C++ port of the reader's
  engine** (verified against the desktop app's Python), the architecture plan,
  and a PlatformIO config.

## The device
A Waveshare **ESP32-S3-Touch-AMOLED-2.41** board (2.41″ AMOLED 600×450,
capacitive touch, USB-C, microSD, LiPo charging) + a ~1000 mAh battery + 3 tactile
buttons, in a custom case (**~58 × 47 × ~17 mm** — barely-there pocket size). It
runs a C++ port of this project's reading core + navigation model.

Books are prepared on a PC by the **desktop app** (which parses TXT/EPUB/PDF) and
copied to the device's microSD; the device reads that prepared text.

## Status
- ✅ Hardware BOM + parametric case — [`hardware/`](hardware/)
- ✅ Reading **engine** ported to C++ and host-verified — [`firmware/`](firmware/)
- ✅ **Navigation** (`Navigator`/`Menu`) ported to C++ and host-verified
- ✅ **Renderer interface** defined (`firmware/src/Renderer.h`)
- ✅ **"Export to SD"** book converter — on the [`main`](../../tree/main) branch
- ⬜ Needs the board: order it → finalize case dimensions; LVGL renderer +
  drivers; input controller; SD/battery/power.

The reading behaviour is shared by design — the pacing rules, the ORP pivot
letter, and the menu model were built UI-agnostic in the desktop app first, so
they port to the firmware. See [`firmware/README.md`](firmware/README.md) and
[`hardware/README.md`](hardware/README.md).
