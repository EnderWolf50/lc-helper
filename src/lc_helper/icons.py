"""The window's icons, drawn on a 24-unit grid in one stroke weight, as pixmaps for the screen's pixel ratio."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

GRID = 24
STROKE = 2  # grid units: a twelfth of the icon's side


def solid(p):
    p.setBrush(p.pen().color())
    p.setPen(Qt.NoPen)


def more(p):
    solid(p)
    for x in (5, 12, 19):
        p.drawEllipse(QPointF(x, 12), 1.8, 1.8)


def unfolded(p):
    p.drawPolyline([QPointF(6, 9), QPointF(12, 15), QPointF(18, 9)])


def folded(p):
    p.drawPolyline([QPointF(9, 6), QPointF(15, 12), QPointF(9, 18)])


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


DRAW = {"more": more, "unfolded": unfolded, "folded": folded, "close": close, "pin": pin, "unpinned": unpinned,
        "play": play, "stop": stop, "dot": dot}


def pixmap(name, color, side, ratio):
    """Icon name in color, side logical pixels square, with ratio device pixels to each: crisp on a scaled screen."""
    pix = QPixmap(round(side * ratio), round(side * ratio))
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(side / GRID, side / GRID)
    p.setPen(QPen(QColor(color), STROKE, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    DRAW[name](p)
    p.end()
    return pix


def icon(name, color, side, ratio):
    return QIcon(pixmap(name, color, side, ratio))
