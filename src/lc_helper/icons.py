"""The window's icons, drawn on a 24-unit grid in one stroke weight, as pixmaps for the screen's pixel ratio."""

from math import cos, pi, sin

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

GRID = 24
STROKE = 2  # grid units: a twelfth of the icon's side


def solid(p):
    p.setBrush(p.pen().color())
    p.setPen(Qt.NoPen)


def gear(p):
    """Eight flat-topped teeth around a ring, and the hole in the middle."""
    rim = QPainterPath()
    for i in range(8):
        for degrees, r in ((-15, 8), (-9, 11), (9, 11), (15, 8)):
            a = (45 * i + degrees) * pi / 180
            point = QPointF(12 + r * cos(a), 12 + r * sin(a))
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
    outer, inner = 11, 11 * sin(pi / 10) / sin(3 * pi / 10)
    middle = 12 + outer * (1 - cos(pi / 5)) / 2
    p.drawPolygon([QPointF(12 + r * sin(i * pi / 5), middle - r * cos(i * pi / 5))
                   for i, r in enumerate([outer, inner] * 5)])


DRAW = {"gear": gear, "box": box, "checked": checked, "unfolded": unfolded, "folded": folded, "up": up, "close": close,
        "pin": pin, "unpinned": unpinned, "play": play, "stop": stop, "dot": dot, "bullet": bullet, "star": star}


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
