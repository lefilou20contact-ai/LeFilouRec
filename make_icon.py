"""Génère icon.png (256x256) et icon.ico sans aucune dépendance."""
import struct, zlib

N = 256
rows = []
for y in range(N):
    row = bytearray([0])
    for x in range(N):
        dx, dy = x - 127.5, y - 127.5
        d = (dx * dx + dy * dy) ** 0.5
        # carré arrondi (rayon 48)
        cx, cy = max(abs(dx) - (128 - 48), 0), max(abs(dy) - (128 - 48), 0)
        inside = (cx * cx + cy * cy) ** 0.5 <= 48
        if not inside:
            px = (0, 0, 0, 0)
        elif d <= 66:
            px = (230, 40, 50, 255)      # point rouge
        elif 86 <= d <= 98:
            px = (240, 240, 240, 255)    # anneau blanc
        else:
            px = (30, 30, 38, 255)
        row += bytes(px)
    rows.append(bytes(row))
raw = b"".join(rows)


def chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
open("icon.png", "wb").write(png)
ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22) + png
open("icon.ico", "wb").write(ico)
print("icon.png / icon.ico générés")
