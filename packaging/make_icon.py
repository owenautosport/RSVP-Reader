"""Write a simple app icon PNG using only the standard library.

A dark square with an orange bar (the RSVP "one word" / pivot motif). Used for
the Linux AppImage, where an icon file is required.

    python3 packaging/make_icon.py out.png [size]
"""

import struct
import sys
import zlib

BG = (17, 17, 17)       # #111111
FG = (232, 100, 60)     # #e8643c (accent)


def make_png(path: str, size: int = 256) -> None:
    bar_top, bar_bot = int(size * 0.44), int(size * 0.56)
    bar_l, bar_r = int(size * 0.30), int(size * 0.70)
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # PNG filter type 0 for this row
        for x in range(size):
            inside = bar_l <= x < bar_r and bar_top <= y < bar_bot
            raw += bytes(FG if inside else BG)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(
            ">I", zlib.crc32(body) & 0xFFFFFFFF
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.png"
    px = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    make_png(out, px)
