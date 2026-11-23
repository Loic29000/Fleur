"""Génère fleur/assets/fleur.ico et fleur.png (icône de l'application).

Usage : python tools/make_icon.py
"""

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QRadialGradient  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "fleur" / "assets"


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = size / 2
    # fond rond sombre (lisible sur barre des tâches claire comme sombre)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1b1e23"))
    p.drawEllipse(QRectF(size * 0.02, size * 0.02, size * 0.96, size * 0.96))
    # cinq pétales roses en dégradé
    for i in range(5):
        a = 2 * math.pi * i / 5 - math.pi / 2
        center = QPointF(c + size * 0.21 * math.cos(a), c + size * 0.21 * math.sin(a))
        grad = QRadialGradient(center, size * 0.2)
        grad.setColorAt(0, QColor("#ffa3c8"))
        grad.setColorAt(1, QColor("#e83e8c"))
        p.setBrush(grad)
        p.drawEllipse(center, size * 0.17, size * 0.17)
    # cœur jaune
    p.setBrush(QColor("#ffd84a"))
    p.drawEllipse(QPointF(c, c), size * 0.12, size * 0.12)
    p.end()
    return img


def main() -> None:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    draw(256).save(str(OUT / "fleur.png"))
    # .ico multi-tailles : Qt écrit l'image donnée ; on assemble les tailles à la main
    import struct
    import io
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    sizes = [16, 24, 32, 48, 64, 128, 256]
    pngs = []
    for s in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        draw(s).save(buf, "PNG")
        pngs.append(bytes(ba.data()))
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, data = b"", b""
    for s, png in zip(sizes, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    (OUT / "fleur.ico").write_bytes(header + entries + data)
    print("icône écrite dans", OUT)


if __name__ == "__main__":
    main()
