#!/usr/bin/env python3
"""Render the HDMI frame-ID pattern with a mouse-driven visible pointer."""

import argparse
import math
import sys
import time
from collections import deque

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

WIDTH = 1280
HEIGHT = 720
RATE = 60
BANDS = (0, HEIGHT * 3 // 10, HEIGHT * 6 // 10, HEIGHT * 9 // 10)
CELL = WIDTH // 10


def paint_pattern(painter, width, height, frame_id, pointer, trail):
    painter.save()
    painter.scale(width / WIDTH, height / HEIGHT)
    painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), QColor(32, 32, 32))
    for top in BANDS:
        painter.fillRect(QRectF(8, top + 8, 32, 32), QColor(224, 224, 224))
        for bit in range(8):
            left = CELL + CELL * bit
            shade = 224 if frame_id & (1 << bit) else 32
            painter.fillRect(QRectF(left + 8, top + 8, CELL - 16, 32),
                             QColor(shade, shade, shade))
    left = frame_id * 7 % WIDTH
    for top, bottom in zip((band + 48 for band in BANDS[:-1]), BANDS[1:]):
        painter.fillRect(QRectF(left, top, 16, bottom - top),
                         QColor(224, 224, 224))
    painter.fillRect(QRectF(0, 0, 4, HEIGHT), QColor(224, 32, 32))
    painter.fillRect(QRectF(WIDTH - 4, 0, 4, HEIGHT), QColor(32, 224, 224))

    # Draw the interactive marker into the source raster.  A compositor may
    # keep its system cursor in a separate plane and omit it from a mirrored
    # output; this marker still follows real mouse events but is guaranteed to
    # be part of the HDMI pixels captured by the receiver.
    for age, point in enumerate(trail):
        alpha = max(32, 180 - age * 18)
        painter.setPen(QPen(QColor(0, 255, 255, alpha), 4))
        painter.drawEllipse(point, 12, 12)
    painter.setPen(QPen(QColor(0, 0, 0), 12))
    painter.drawEllipse(pointer, 30, 30)
    painter.drawLine(QPointF(pointer.x() - 42, pointer.y()),
                     QPointF(pointer.x() + 42, pointer.y()))
    painter.drawLine(QPointF(pointer.x(), pointer.y() - 42),
                     QPointF(pointer.x(), pointer.y() + 42))
    painter.setPen(QPen(QColor(0, 255, 255), 7))
    painter.drawEllipse(pointer, 30, 30)
    painter.drawLine(QPointF(pointer.x() - 42, pointer.y()),
                     QPointF(pointer.x() + 42, pointer.y()))
    painter.drawLine(QPointF(pointer.x(), pointer.y() - 42),
                     QPointF(pointer.x(), pointer.y() + 42))
    painter.setBrush(QColor(255, 32, 255))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(pointer, 7, 7)
    painter.restore()


class PatternWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.started = time.monotonic()
        self.frame_id = 0
        self.pointer = QPointF(WIDTH / 2, HEIGHT / 2)
        self.trail = deque(maxlen=8)
        self.last_logged = None
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.advance)
        self.timer.start(8)

    def advance(self):
        self.frame_id = int((time.monotonic() - self.started) * RATE) % 256
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        point = QPointF(pos.x() * WIDTH / max(1, self.width()),
                        pos.y() * HEIGHT / max(1, self.height()))
        self.pointer = point
        if (self.last_logged is None or
                math.hypot(point.x() - self.last_logged.x(),
                           point.y() - self.last_logged.y()) >= 4):
            self.trail.appendleft(QPointF(point))
            self.last_logged = QPointF(point)
            print(f"POINTER {point.x():.1f} {point.y():.1f}", flush=True)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_pattern(painter, self.width(), self.height(), self.frame_id,
                      self.pointer, self.trail)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--screen", required=True,
                    help="Qt output name on which to open fullscreen")
    ap.add_argument("--self-test", action="store_true",
                    help="render one offscreen frame and exit")
    args = ap.parse_args()

    app = QApplication(sys.argv[:1])
    if args.self_test:
        image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        paint_pattern(painter, WIDTH, HEIGHT, 85, QPointF(640, 360),
                      [QPointF(600, 340), QPointF(560, 320)])
        painter.end()
        if image.isNull() or image.pixelColor(640, 360) != QColor(255, 32, 255):
            raise SystemExit("offscreen pointer render failed")
        print("interactive pattern self-test passed")
        return

    screen = next((item for item in QGuiApplication.screens()
                   if item.name() == args.screen), None)
    if screen is None:
        names = ", ".join(item.name() for item in QGuiApplication.screens())
        raise SystemExit(f"screen {args.screen!r} not found; available: {names}")
    widget = PatternWidget()
    widget.create()
    widget.windowHandle().setScreen(screen)
    widget.setGeometry(screen.geometry())
    widget.showFullScreen()
    print(f"READY screen={screen.name()} geometry="
          f"{screen.geometry().width()}x{screen.geometry().height()}", flush=True)
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
