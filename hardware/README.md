# RSVP Pocket Reader — hardware

The pocket device: a tiny, true-black, touch + 3-button RSVP reader built on an
ESP32-S3 board (the same family as the open-source RSVP Nano). This project's
desktop app is its companion + book loader; the device itself runs firmware
(RSVP Nano, or a fork that adds the 3 buttons and our menu UX).

## Bill of materials

| Part | Choice | Notes |
|------|--------|-------|
| **Brain + screen** | Waveshare **ESP32-S3-Touch-AMOLED-2.41** | 2.41″ AMOLED 600×450 landscape, cap touch, USB-C, microSD slot, MX1.25 LiPo header, IMU + RTC, 34-pin GPIO header |
| **Battery** | ~1000 mAh LiPo, 3.7 V, **MX1.25** plug | ~7–10 h reading; days of standby. Match the board's MX1.25 connector |
| **Buttons** | 3× low-profile tactile switches + 3D-printed caps | Slower · Play/Pause · Faster, on the top edge, wired to 3 GPIO |
| **Storage** | 16 GB microSD (FAT32) | books are tiny; 8 GB is plenty too |
| **Case** | custom 3D print — `case.scad` | two-part clamshell |
| Misc | MX1.25 lead, hookup wire | — |

Charging, USB data (book transfer), the microSD slot, and a power button are all
already on the board.

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

## Wiring (firmware fork)

- **3 buttons** → 3 free GPIO on the 34-pin header (internal pull-ups; or a
  single-ADC resistor ladder if pins get tight).
- Display (QSPI), touch (I²C), microSD, IMU, RTC, and battery gauge are already
  on-board — the firmware reads the fuel gauge / RTC over their buses.

## Software relationship

The device firmware is separate from this repo's Python app, but the **reading
behaviour is shared by design**: the pacing rules, the ORP pivot letter, and the
menu model were all built here first (UI-agnostic core) so they port to the
firmware. The desktop app also prepares/loads books onto the device.
