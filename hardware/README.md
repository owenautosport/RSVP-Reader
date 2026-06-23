# RSVP Pocket Reader — hardware

The pocket device: a tiny, true-black, touch + 3-button RSVP reader built on an
ESP32-S3 board (the same family as the open-source RSVP Nano). This project's
desktop app is its companion + book loader; the device runs a **C++ port of our
own software** (see [`../firmware`](../firmware)) — our reading core and nav
model, not a fork of RSVP Nano.

## Bill of materials

| Part | Choice | ~Price | Notes |
|------|--------|--------|-------|
| **Brain + screen** | Waveshare **ESP32-S3-Touch-AMOLED-2.41** | ~$38 | 2.41″ AMOLED 600×450 landscape, cap touch, USB-C, microSD slot, MX1.25 LiPo header, IMU + RTC, 34-pin GPIO header |
| **Battery** | 3.7 V ~1000 mAh LiPo | ~$9 | ~7–10 h reading; days of standby. See *battery connector* below |
| **Buttons** | 3× low-profile / side-actuated tactile switches + 3D-printed caps | ~$7 | Slower · Play/Pause · Faster, top edge, wired to 3 GPIO |
| **Storage** | 16 GB microSD (FAT32) | ~$7 | books are tiny; 8 GB is plenty too |
| **MX1.25 pigtail** | 2-pin 1.25 mm lead (if the battery doesn't have one) | ~$6 | to match the board's connector |
| **Case** | custom 3D print — `case.scad` | filament | two-part clamshell |
| Misc | hookup wire | — | — |

**Total ≈ $60–70** + filament. Charging, USB data (book transfer), the microSD
slot, and a power button are all already on the board.

### Battery connector
The board's battery header is **MX1.25 (1.25 mm)**, but most ~1000 mAh LiPos ship
with a **JST-PH 2.0 mm** plug. So either get a cell with a 1.25 mm plug, or fit an
MX1.25 pigtail and re-pin. ⚠️ LiPo connector polarity isn't standardized — confirm
**+/−** against the board before plugging in.

## Estimated size

Active screen ~49 × 37 mm. In the case, roughly **~58 × 47 × ~17 mm** — barely-there
pocket size, smaller than a Canon 90D flip screen, true-black AMOLED.

## Case — `case.scad`

Parametric OpenSCAD clamshell. **The board outline is an estimate** — measure the
real board (or use the datasheet) and update the six `board_*` / `screen_*`
values at the top, then re-render. Print `front_shell()` and `back_shell()`
separately (set `SHOW`).

It models: the screen window, 3 top-edge button holes, USB-C cutout (bottom),
microSD cutout (side), board-seating posts, and a battery pocket.

⚠️ Confirm before printing: the board's exact outline (W×H×thickness), the active
area's offset, and which edges the USB-C and microSD sit on — these drive every
cutout position.

## Wiring (firmware)

- **3 buttons** → 3 free GPIO on the 34-pin header (internal pull-ups; or a
  single-ADC resistor ladder if pins get tight).
- Display (QSPI), touch (I²C), microSD, IMU, RTC, and battery gauge are already
  on-board — the firmware reads the fuel gauge / RTC over their buses.

## Software relationship

The device firmware is separate from this repo's Python app, but the **reading
behaviour is shared by design**: the pacing rules, the ORP pivot letter, and the
menu model were all built here first (UI-agnostic core) so they port to the
firmware. The desktop app also prepares/loads books onto the device.
