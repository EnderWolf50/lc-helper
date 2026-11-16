"""The window's icons, drawn on a 24-unit grid in one stroke weight, and the game's keyword icons, sin icons and gift
pictures, as pixmaps for the screen's pixel ratio."""

from functools import cache
import math
from math import pi

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform

from . import paths
from .palette import INK, display_family

GRID = 24
STROKE = 2  # grid units: a twelfth of the icon's side
KEYWORDLESS = INK["line-2"]  # the ring for a gift of no keyword: quiet beside the game's coloured icons
# Each of events.SINS and its icon's file in the package's data/sin_icons.
SIN_ICONS = {"暴怒": "Wrath", "色慾": "Lust", "怠惰": "Sloth", "暴食": "Gluttony", "憂鬱": "Gloom", "傲慢": "Pride",
             "嫉妒": "Envy"}


def solid(p):
    p.setBrush(p.pen().color())
    p.setPen(Qt.NoPen)


def gear(p):
    """Eight flat-topped teeth around a ring, and the hole in the middle."""
    rim = QPainterPath()
    for i in range(8):
        for degrees, r in ((-15, 8), (-9, 11), (9, 11), (15, 8)):
            a = (45 * i + degrees) * pi / 180
            point = QPointF(12 + r * math.cos(a), 12 + r * math.sin(a))
            rim.lineTo(point) if rim.elementCount() else rim.moveTo(point)
    rim.closeSubpath()
    p.drawPath(rim)
    p.drawEllipse(QPointF(12, 12), 3.2, 3.2)


def box(p):
    """A check box, off."""
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)


def checked(p):
    """A check box, on: filled, the tick cut out of it, so the background shows through."""
    solid(p)
    p.drawRoundedRect(QRectF(3, 3, 18, 18), 4, 4)
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    p.setPen(QPen(Qt.black, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawPolyline([QPointF(7.5, 12.5), QPointF(10.5, 15.5), QPointF(16.5, 9)])


def unfolded(p):
    p.drawPolyline([QPointF(6, 9), QPointF(12, 15), QPointF(18, 9)])


def folded(p):
    p.drawPolyline([QPointF(9, 6), QPointF(15, 12), QPointF(9, 18)])


def up(p):
    p.drawPolyline([QPointF(6, 15), QPointF(12, 9), QPointF(18, 15)])


def close(p):
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))


def pin(p):
    body = QPainterPath(QPointF(5, 17))
    for x, y in ((19, 17), (19, 15.5), (15, 12.5), (15, 6), (16, 6), (16, 2.5), (8, 2.5), (8, 6), (9, 6), (9, 12.5),
                 (5, 15.5)):
        body.lineTo(x, y)
    body.closeSubpath()
    p.drawPath(body)
    p.drawLine(QPointF(12, 17), QPointF(12, 22))


def unpinned(p):
    """The pin tilted, as one lying loose."""
    p.translate(12, 12)
    p.rotate(45)
    p.translate(-12, -12)
    pin(p)


def play(p):
    solid(p)
    p.drawPolygon([QPointF(7, 4.5), QPointF(19.5, 12), QPointF(7, 19.5)])


def stop(p):
    solid(p)
    p.drawRoundedRect(6, 6, 12, 12, 1.5, 1.5)


def search(p):
    """A lens with its handle to the lower right."""
    p.drawEllipse(QPointF(10.5, 10.5), 6, 6)
    p.drawLine(QPointF(15, 15), QPointF(20, 20))


def ring(p):
    """An empty ring: no keyword."""
    p.drawEllipse(QPointF(12, 12), 6, 6)


def dot(p):
    solid(p)
    p.drawEllipse(QPointF(12, 12), 10, 10)


def bullet(p):
    solid(p)
    p.drawEllipse(QPointF(12, 12), 4.5, 4.5)


def star(p):
    """Five points, filled, the tips blunted by the round-joined stroke. The centre sits low, so the top point and
    the two feet end equally far from the top and bottom edges."""
    p.setBrush(p.pen().color())
    outer, inner = 11, 11 * math.sin(pi / 10) / math.sin(3 * pi / 10)
    middle = 12 + outer * (1 - math.cos(pi / 5)) / 2
    p.drawPolygon([QPointF(12 + r * math.sin(i * pi / 5), middle - r * math.cos(i * pi / 5))
                   for i, r in enumerate([outer, inner] * 5)])


DRAW = {"gear": gear, "box": box, "checked": checked, "unfolded": unfolded, "folded": folded, "up": up, "close": close,
        "pin": pin, "unpinned": unpinned, "play": play, "stop": stop, "dot": dot, "bullet": bullet, "star": star,
        "search": search, "ring": ring}


def paint(p, name, color, square: QRectF):
    """Icon name in color, drawn by p into square."""
    p.save()
    p.translate(square.topLeft())
    p.scale(square.width() / GRID, square.height() / GRID)
    p.setPen(QPen(QColor(color), STROKE, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    DRAW[name](p)
    p.restore()


def pixmap(name, color, side, ratio):
    """Icon name in color, side logical pixels square, with ratio device pixels to each: crisp on a scaled screen."""
    pix = QPixmap(round(side * ratio), round(side * ratio))
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    paint(p, name, color, QRectF(0, 0, side, side))
    p.end()
    return pix


def icon(name, color, side, ratio):
    return QIcon(pixmap(name, color, side, ratio))


def chamfered(rect: QRectF, cut) -> QPainterPath:
    """rect with each corner cut off at 45 degrees, cut pixels along each side: the frames of the game and of maalc."""
    left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
    path = QPainterPath(QPointF(left + cut, top))
    for x, y in ((right - cut, top), (right, top + cut), (right, bottom - cut), (right - cut, bottom),
                 (left + cut, bottom), (left, bottom - cut), (left, top + cut)):
        path.lineTo(x, y)
    path.closeSubpath()
    return path


def fitted(image, side, ratio):
    """image fitted whole and centred in a square side logical pixels across, with ratio device pixels to each."""
    pix = QPixmap(round(side * ratio), round(side * ratio))
    pix.fill(Qt.transparent)
    scaled = image.scaled(pix.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    p = QPainter(pix)
    p.drawImage((pix.width() - scaled.width()) // 2, (pix.height() - scaled.height()) // 2, scaled)
    p.end()
    pix.setDevicePixelRatio(ratio)  # after painting: the painter worked in device pixels
    return pix


def inked(pix):
    """pix cut to the rows its drawing takes, with no empty rows above or below it."""
    image = pix.toImage().convertToFormat(QImage.Format_ARGB32)
    alpha = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())
    rows = np.flatnonzero(alpha[:, 3:image.width() * 4:4].any(axis=1))  # ARGB32 is B, G, R, A in memory
    if not len(rows):
        return pix
    out = pix.copy(0, int(rows[0]), pix.width(), int(rows[-1] - rows[0] + 1))
    out.setDevicePixelRatio(pix.devicePixelRatio())
    return out


def padded_below(pix, extra):
    """pix over a transparent strip extra logical pixels tall, at pix's ratio of device pixels to logical ones."""
    ratio = pix.devicePixelRatio()
    out = QPixmap(pix.width(), pix.height() + round(extra * ratio))
    out.setDevicePixelRatio(ratio)  # before painting: pix is drawn at its logical size, which is then its own
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, pix)
    p.end()
    return out


@cache
def game_icon(keyword):
    """The game's picture for keyword (the package's data/keyword_icons), at the size it comes in; null for a keyword
    without one."""
    return QImage(str(paths.PACKAGE / "data/keyword_icons" / f"{keyword}.webp"))


def keyword(name, side, ratio):
    """The game's icon for keyword name, fitted whole and centred in a square side logical pixels across, with ratio
    device pixels to each; a quiet ring for a keyword the game draws none for (Keywordless)."""
    if game_icon(name).isNull():
        return pixmap("ring", KEYWORDLESS, side, ratio)
    return fitted(game_icon(name), side, ratio)


@cache
def sin_picture(name):
    """The game's emblem for sin name, one of events.SINS (the package's data/sin_icons), at the size it comes in."""
    return QImage(str(paths.PACKAGE / "data/sin_icons" / f"{SIN_ICONS[name]}.png"))


def sin(name, side, ratio):
    """The game's emblem for sin name, as a Choices page draws it, fitted whole and centred in a square side logical
    pixels across, with ratio device pixels to each."""
    return fitted(sin_picture(name), side, ratio)


@cache
def gift_picture(gift_id):
    """The game's picture of gift gift_id (the package's data/gift_icons), at the size it comes in; null when there is
    none."""
    return QImage(str(paths.PACKAGE / "data/gift_icons" / f"{gift_id}.webp"))


BADGE = 0.45  # the keyword icon's share of a gift picture's side, in its bottom-right corner
# The slot a gift's picture sits in: a dark square, its corners cut, with a thin edge (maalc's gift tile), so a thin
# drawing (a gauntlet seen edge on) reads as the same size as a bulky one. Its corners' cut and the picture's margin
# inside it, as shares of the side.
SLOT_FILL, SLOT_EDGE, SLOT_CUT, SLOT_INSET = INK["bg"], INK["card-line"], 0.12, 0.07
# The game's gift slot (its prefab EgoGiftIconPrefab; maalc's tools/gift_slot.py holds the same numbers and checks
# them against the client: change both together), in its units: the plate fills the slot; the picture is a square this wide, this far above the middle; the keyword's icon is a
# square this wide, this far in from the bottom-right corner.
SLOT = {"slot": 350, "picture": 256, "picture_rise": 8, "keyword": 100, "keyword_in": 5}
# The slot's tier: the game's text colour (tmp_Tier, #F8C200) in maalc's condensed face, with the glow of the game's
# material (its underlay, (0.689, 0.108, 0)) as a soft edge. Its drawing's left and top edges and height as shares of
# the side, as the game's Gift GET page draws it (maalc tests/screens/GiftGet.png: II at x 352-368, y 234-271 on a
# 144 px slot), and the face narrowed to the game's II (0.118 of the side; Barlow Condensed's is 0.139).
TIER_FILL, TIER_GLOW = "#f8c200", QColor(0xb0, 0x1c, 0x00, 200)
TIER_LEFT, TIER_TOP, TIER_HEIGHT, TIER_NARROW = 0.097, 0.062, 0.264, 0.85


@cache
def plate():
    """The game's striped plate a gift sits on in its slot (the package's data/gift_slot)."""
    return QImage(str(paths.PACKAGE / "data/gift_slot/plate.png"))


def game_gift(gift_id, kw, side, ratio, tier=""):
    """A gift as the game draws it in its slot (the shop, a Gift GET page, the Gift Search), a square side logical
    pixels across, with ratio device pixels to each: its picture on the game's striped plate, its tier (a Roman
    numeral) in the top-left corner and its keyword kw's icon in the bottom-right, none for a gift of no keyword. The
    keyword's icon alone when the game has no picture of the gift."""
    if gift_picture(gift_id).isNull():
        return keyword(kw, side, ratio)
    n = round(side * ratio)
    unit = n / SLOT["slot"]
    pix = QPixmap(n, n)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    p.drawImage(QRectF(0, 0, n, n), plate())
    box = round(SLOT["picture"] * unit)
    picture = gift_picture(gift_id).scaled(box, box, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    p.drawImage(QPointF((n - picture.width()) / 2, (n - picture.height()) / 2 - SLOT["picture_rise"] * unit), picture)
    if not game_icon(kw).isNull():
        box, inset = round(SLOT["keyword"] * unit), SLOT["keyword_in"] * unit
        icon = game_icon(kw).scaled(box, box, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawImage(QPointF(n - inset - (box + icon.width()) / 2, n - inset - (box + icon.height()) / 2), icon)
    if tier:
        font = QFont(display_family(700))
        font.setBold(True)
        font.setPixelSize(100)  # any size: the drawing is scaled to TIER_HEIGHT
        path = QPainterPath()
        path.addText(0, 0, font, tier)
        ink = path.boundingRect()
        scale = TIER_HEIGHT * n / ink.height()
        path = QTransform().translate(TIER_LEFT * n, TIER_TOP * n).scale(scale * TIER_NARROW, scale).translate(
            -ink.left(), -ink.top()).map(path)
        p.strokePath(path, QPen(TIER_GLOW, max(1.0, n * 0.02), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.fillPath(path, QColor(TIER_FILL))
    p.end()
    pix.setDevicePixelRatio(ratio)  # after painting: the painter worked in device pixels
    return pix


def gift(gift_id, kw, side, ratio, badge=True):
    """The game's picture of a gift in maalc's tile, a square side logical pixels across, with ratio device pixels to
    each; the picture fitted whole and centred inside the tile's margin. With badge, its keyword kw's icon in the
    bottom-right corner, as the game's shop marks a gift. The keyword's icon alone when the game has no picture of the
    gift."""
    if gift_picture(gift_id).isNull():
        return keyword(kw, side, ratio)
    pix = QPixmap(round(side * ratio), round(side * ratio))
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    edge = max(1.0, ratio)  # one logical pixel
    p.setPen(QPen(QColor(SLOT_EDGE), edge))
    p.setBrush(QColor(SLOT_FILL))
    p.drawPath(chamfered(QRectF(edge / 2, edge / 2, pix.width() - edge, pix.height() - edge), pix.width() * SLOT_CUT))
    inset = round(pix.width() * SLOT_INSET + edge)
    picture = gift_picture(gift_id).scaled(pix.width() - 2 * inset, pix.height() - 2 * inset, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
    p.drawImage((pix.width() - picture.width()) // 2, (pix.height() - picture.height()) // 2, picture)
    if badge:
        corner = keyword(kw, side * BADGE, ratio)
        # in device pixels, as the painter works: drawn at a point, Qt would shrink it to its logical size
        p.drawPixmap(QRectF(pix.width() - corner.width(), pix.height() - corner.height(), corner.width(),
                            corner.height()), corner, QRectF(corner.rect()))
    p.end()
    pix.setDevicePixelRatio(ratio)  # after painting: the painter worked in device pixels
    return pix


def gift_icon(gift_id, kw, side, ratio):
    """A gift's picture with its keyword badge as a QIcon that keeps its colours on a lit list row."""
    pix = gift(gift_id, kw, side, ratio)
    icon = QIcon(pix)
    icon.addPixmap(pix, QIcon.Selected)
    return icon


def keyword_icon(name, side, ratio):
    """keyword's icon as a QIcon that keeps its colours on a lit list row or menu item, which Qt would tint."""
    pix = keyword(name, side, ratio)
    icon = QIcon(pix)
    icon.addPixmap(pix, QIcon.Selected)
    return icon
