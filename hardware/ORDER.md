# Order list — chosen parts (UK)

The specific parts ordered for this build. (Links live here; the BOM in
`README.md` stays link-free.)

| Part | Product | Notes |
|------|---------|-------|
| **Brain + screen** | Waveshare ESP32-S3-Touch-AMOLED-2.41 — <https://www.waveshare.com/esp32-s3-touch-amoled-2.41.htm> | the reader brain (AMOLED + touch + USB-C + microSD + LiPo charging) |
| **Battery** | 1000 mAh LiPo — <https://www.amazon.co.uk/dp/B0F6CT3KTQ> | confirm connector + that it fits behind the board |
| **Battery connector** | Didamx MX1.25 pre-crimped leads — <https://www.amazon.co.uk/dp/B0D69R2Y8P> | to match the board's 1.25 mm header |
| **Buttons** | Tactile momentary switch assortment — <https://www.amazon.co.uk/dp/B0DYDQ5SV2> | use 3 (Slower · Play/Pause · Faster) |
| **Wire** | Striveday silicone hookup wire — <https://www.amazon.co.uk/dp/B01KQ2JNLI> | button wiring |
| **microSD** | already owned | format FAT32 |
| **Filament** | already owned | the case |

## Before assembly — checklist
- ⚠️ **Battery polarity:** the LiPo and the board both use small 2-pin plugs, but
  LiPo polarity isn't standardized. Use the **Didamx MX1.25 pre-crimped leads** to
  make the board-side lead, and **confirm + / − against the board's silkscreen**
  before the first connection — wrong polarity can kill the board.
- **Battery fit:** confirm the cell is ≈ 40 × 30 × 6 mm or smaller so it sits
  behind the board inside the case.
- **Case:** measure the real board (W × H × thickness, port positions) and update
  the `board_*` / `screen_*` values in `case.scad` before printing.
