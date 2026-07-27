from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut, QConicalGradient,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar, QGraphicsDropShadowEffect,
)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1100, 720
_MIN_W,     _MIN_H     = 900, 600
_LEFT_W  = 160
_RIGHT_W = 360

_OS = platform.system()


# ---------------------------------------------------------------------------
# Color palette — deep navy + cyan + orange + teal
# ---------------------------------------------------------------------------
class C:
    BG        = "#000814"
    BG2       = "#000d1a"
    PANEL     = "#00111f"
    PANEL2    = "#001524"
    BORDER    = "#0a2540"
    BORDER_B  = "#0e4060"
    BORDER_A  = "#0a3050"
    PRI       = "#00b4d8"      # cyan
    PRI_DIM   = "#005f7a"
    PRI_GHO   = "#001825"
    ACC       = "#f77f00"      # orange
    ACC2      = "#ffd60a"      # gold
    TEAL      = "#06d6a0"      # teal / listening
    TEAL_D    = "#03785a"
    RED       = "#ef233c"
    MUTED_C   = "#ef233c"
    PURPLE    = "#7b2d8b"
    TEXT      = "#90e0ef"
    TEXT_DIM  = "#2a6070"
    TEXT_MED  = "#48a0b8"
    WHITE     = "#caf0f8"
    DARK      = "#00060f"
    CORE      = "#ffffff"
    CORE_GLO  = "#00b4d8"
    HEX_LINE  = "#041828"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(a)
    return c


# ---------------------------------------------------------------------------
# System metrics
# ---------------------------------------------------------------------------
class _SysMetrics:
    def __init__(self):
        self.cpu = 0.0
        self.mem = 0.0
        self.net = 0.0
        self.gpu = -1.0
        self.tmp = -1.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now
        gpu = self._get_gpu()
        tmp = self._get_temp()
        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass
        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz"]:
                if name in temps and temps[name]:
                    return temps[name][0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass
        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {"cpu": self.cpu, "mem": self.mem, "net": self.net,
                    "gpu": self.gpu, "tmp": self.tmp}


_metrics = _SysMetrics()


# ---------------------------------------------------------------------------
# Dot Sphere HUD — the main visual
# ---------------------------------------------------------------------------
class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"

        self._tick        = 0
        self._rot_x       = 0.0   # sphere rotation angles
        self._rot_y       = 0.0
        self._rot_z       = 0.0
        self._energy      = 0.3   # 0.0 = idle, 1.0 = full speaking
        self._tgt_energy  = 0.3
        self._halo        = 40.0
        self._tgt_halo    = 40.0
        self._blink       = True
        self._blink_tick  = 0
        self._scan        = 0.0
        self._wave_phase  = 0.0
        self._particles: list[list[float]] = []

        # Waveform bars (outer ring)
        self._wave_bars   = [0.0] * 64

        # Dot sphere points — golden ratio spiral on sphere
        self._sphere_pts  = self._make_sphere(320)

        # Morphing offsets per point
        self._morph = [0.0] * len(self._sphere_pts)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)  # ~60fps

    def _make_sphere(self, n: int) -> list[tuple[float, float, float]]:
        """Golden ratio sphere points."""
        pts = []
        golden = math.pi * (3.0 - math.sqrt(5.0))
        for i in range(n):
            y   = 1.0 - (i / (n - 1)) * 2.0
            r   = math.sqrt(1.0 - y * y)
            phi = golden * i
            x   = math.cos(phi) * r
            z   = math.sin(phi) * r
            pts.append((x, y, z))
        return pts

    def _project(self, x, y, z, cx, cy, r, rx, ry, rz) -> tuple[float, float, float]:
        """Rotate point and project to 2D. Returns (px, py, depth)."""
        # Rotate Y
        cos_y, sin_y = math.cos(ry), math.sin(ry)
        x2 = x * cos_y + z * sin_y
        z2 = -x * sin_y + z * cos_y

        # Rotate X
        cos_x, sin_x = math.cos(rx), math.sin(rx)
        y2 = y * cos_x - z2 * sin_x
        z3 = y * sin_x + z2 * cos_x

        # Rotate Z
        cos_z, sin_z = math.cos(rz), math.sin(rz)
        x3 = x2 * cos_z - y2 * sin_z
        y3 = x2 * sin_z + y2 * cos_z

        depth = (z3 + 1.0) / 2.0
        px = cx + x3 * r
        py = cy + y3 * r
        return px, py, depth, z3

    def _step(self):
        self._tick += 1

        # Energy smoothing
        if self.speaking:
            self._tgt_energy = random.uniform(0.6, 1.0)
            self._tgt_halo   = random.uniform(160, 220)
        elif self.muted:
            self._tgt_energy = 0.05
            self._tgt_halo   = 15.0
        elif self.state == "THINKING":
            self._tgt_energy = random.uniform(0.25, 0.45)
            self._tgt_halo   = random.uniform(60, 100)
        else:
            self._tgt_energy = 0.2 + 0.08 * math.sin(self._tick * 0.04)
            self._tgt_halo   = 40.0 + 15.0 * math.sin(self._tick * 0.03)

        sp = 0.25 if self.speaking else 0.08
        self._energy += (self._tgt_energy - self._energy) * sp
        self._halo   += (self._tgt_halo   - self._halo)   * 0.1

        # Rotation speeds by state
        if self.speaking:
            self._rot_y += 0.018
            self._rot_x += 0.006
            self._rot_z += 0.003
        elif self.muted:
            self._rot_y += 0.004
        else:
            self._rot_y += 0.008
            self._rot_x += 0.002

        # Morph offsets — dots ripple outward when speaking
        for i in range(len(self._morph)):
            if self.speaking:
                target = random.uniform(-0.12, 0.22) * self._energy
            else:
                target = 0.04 * math.sin(self._tick * 0.05 + i * 0.3) * self._energy
            self._morph[i] += (target - self._morph[i]) * 0.15

        # Waveform bars
        for i in range(len(self._wave_bars)):
            if self.speaking:
                target = random.uniform(0.1, 1.0) * self._energy
            elif self.state == "THINKING":
                target = 0.3 + 0.2 * math.sin(self._tick * 0.08 + i * 0.4)
            else:
                target = 0.05 + 0.08 * math.sin(self._tick * 0.06 + i * 0.5)
            self._wave_bars[i] += (target - self._wave_bars[i]) * 0.2

        # Scan line
        self._scan = (self._scan + (2.5 if self.speaking else 1.0)) % 360
        self._wave_phase += 0.05

        # Particles when speaking
        fw = min(self.width(), self.height())
        if self.speaking and random.random() < 0.4:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.22
            spd = random.uniform(1.5, 4.0) * self._energy
            self._particles.append([
                cx + math.cos(ang) * r_s,
                cy + math.sin(ang) * r_s,
                math.cos(ang) * spd,
                math.sin(ang) * spd,
                1.0,
                random.choice([C.PRI, C.ACC, C.TEAL, C.ACC2])
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.96, p[3]*0.96, p[4]-0.022, p[5]]
            for p in self._particles if p[4] > 0
        ]

        # Blink
        self._blink_tick += 1
        if self._blink_tick >= 35:
            self._blink = not self._blink
            self._blink_tick = 0

        self.update()

    def _state_colors(self) -> tuple[str, str, str]:
        """Returns (primary, secondary, core) colors for current state."""
        if self.muted:
            return C.RED, "#660011", C.RED
        elif self.speaking:
            return C.ACC, C.PRI, C.ACC2
        elif self.state == "THINKING":
            return C.ACC2, C.ACC, "#ffffff"
        elif self.state == "LISTENING":
            return C.TEAL, C.PRI, C.TEAL
        else:
            return C.PRI, C.PRI_DIM, C.CORE

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        pri, sec, core_col = self._state_colors()

        # ── Hex grid background ──
        self._draw_hex_grid(p, W, H, pri)

        # ── Outer waveform ring ──
        self._draw_waveform_ring(p, cx, cy, fw, pri, sec)

        # ── Glow halo rings ──
        self._draw_halo(p, cx, cy, fw, pri)

        # ── Dot sphere ──
        self._draw_dot_sphere(p, cx, cy, fw, pri, sec)

        # ── Arc reactor core ──
        self._draw_core(p, cx, cy, fw, core_col, pri)

        # ── Scan line ──
        self._draw_scan(p, cx, cy, fw, pri)

        # ── Corner brackets ──
        self._draw_brackets(p, cx, cy, fw, pri)

        # ── Particles ──
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(pt[5], a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.0, 2.0)

        # ── Status text ──
        self._draw_status(p, cx, cy, fw, pri)

    def _draw_hex_grid(self, p: QPainter, W, H, pri):
        hex_size = 32
        col = qcol(C.HEX_LINE, 180)
        p.setPen(QPen(col, 0.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        dx = hex_size * 1.732
        dy = hex_size * 1.5
        cols_n = int(W / dx) + 2
        rows_n = int(H / dy) + 2
        for row in range(-1, rows_n + 1):
            for col_n in range(-1, cols_n + 1):
                offset_x = (hex_size * 0.866) if row % 2 else 0
                hx = col_n * dx + offset_x
                hy = row * dy
                path = QPainterPath()
                for i in range(6):
                    ang = math.radians(60 * i - 30)
                    px2 = hx + hex_size * 0.85 * math.cos(ang)
                    py2 = hy + hex_size * 0.85 * math.sin(ang)
                    if i == 0:
                        path.moveTo(px2, py2)
                    else:
                        path.lineTo(px2, py2)
                path.closeSubpath()
                p.drawPath(path)

    def _draw_waveform_ring(self, p: QPainter, cx, cy, fw, pri, sec):
        """Circular waveform bars around the sphere."""
        n     = len(self._wave_bars)
        r_in  = fw * 0.44
        r_max = fw * 0.52
        for i, bar in enumerate(self._wave_bars):
            ang = math.radians((i / n) * 360 - 90)
            bar_h = bar * (r_max - r_in)
            r_out = r_in + bar_h
            x1 = cx + r_in  * math.cos(ang)
            y1 = cy + r_in  * math.sin(ang)
            x2 = cx + r_out * math.cos(ang)
            y2 = cy + r_out * math.sin(ang)
            # Color gradient: cyan → orange based on height
            frac = bar
            if frac > 0.7:
                color = qcol(C.ACC, int(200 + 55 * frac))
            elif frac > 0.4:
                color = qcol(C.ACC2, int(180 + 50 * frac))
            else:
                color = qcol(pri, int(120 + 100 * frac))
            p.setPen(QPen(color, 2.5))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_halo(self, p: QPainter, cx, cy, fw, pri):
        for i in range(8, 0, -1):
            r   = fw * (0.44 + i * 0.015)
            frc = 1.0 - i / 8
            a   = max(0, min(255, int(self._halo * 0.06 * frc)))
            p.setPen(QPen(qcol(pri, a), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    def _draw_dot_sphere(self, p: QPainter, cx, cy, fw, pri, sec):
        """The main dot sphere with morphing."""
        r_sphere = fw * 0.30
        rx = self._rot_x
        ry = self._rot_y
        rz = self._rot_z

        # Sort by depth for correct rendering
        projected = []
        for i, (x, y, z) in enumerate(self._sphere_pts):
            morph = self._morph[i]
            nx = x * (1.0 + morph)
            ny = y * (1.0 + morph)
            nz = z * (1.0 + morph)
            px, py, depth, z3 = self._project(nx, ny, nz, cx, cy, r_sphere, rx, ry, rz)
            projected.append((px, py, depth, morph, z3))

        # Draw from back to front
        projected.sort(key=lambda v: v[2])

        for px, py, depth, morph, z3 in projected:
            # Dot size based on depth + morph
            base_size = 1.2 + depth * 1.8
            dot_size  = base_size * (1.0 + abs(morph) * 2.0)

            # Color based on depth and state
            a = int(60 + depth * 180)
            if self.speaking:
                if depth > 0.7:
                    col = qcol(C.ACC, a)
                elif depth > 0.4:
                    col = qcol(C.ACC2, a)
                else:
                    col = qcol(pri, a)
            elif self.muted:
                col = qcol(C.RED, a)
            elif self.state == "THINKING":
                col = qcol(C.ACC2 if depth > 0.5 else pri, a)
            else:
                col = qcol(C.TEAL if depth > 0.6 else pri, a)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(px, py), dot_size, dot_size)

    def _draw_core(self, p: QPainter, cx, cy, fw, core_col, pri):
        """Arc reactor core at center."""
        # Outer glow
        for i in range(6, 0, -1):
            r   = fw * 0.10 * (i / 6) * (1.0 + self._energy * 0.3)
            a   = int(self._halo * 0.12 * (1.0 - i / 6))
            p.setPen(Qt.PenStyle.NoPen)
            g = QRadialGradient(cx, cy, r)
            g.setColorAt(0, qcol(core_col, a * 2))
            g.setColorAt(1, qcol(core_col, 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(cx, cy), r, r)

        # Concentric rings
        ring_radii = [fw * 0.065, fw * 0.085, fw * 0.10]
        for i, r in enumerate(ring_radii):
            a = int(150 + 80 * self._energy)
            p.setPen(QPen(qcol(pri if i < 2 else core_col, a), 1.5 if i < 2 else 2.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)

        # Rotating inner spokes
        n_spokes = 6
        for i in range(n_spokes):
            ang = math.radians(i * (360 / n_spokes) + self._rot_y * 30)
            r1, r2 = fw * 0.025, fw * 0.06
            p.setPen(QPen(qcol(pri, 160), 1.0))
            p.drawLine(
                QPointF(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1),
                QPointF(cx + math.cos(ang) * r2, cy + math.sin(ang) * r2),
            )

        # Bright center dot
        p.setPen(Qt.PenStyle.NoPen)
        g2 = QRadialGradient(cx, cy, fw * 0.025)
        g2.setColorAt(0, qcol(C.WHITE, 255))
        g2.setColorAt(0.3, qcol(core_col, 220))
        g2.setColorAt(1, qcol(core_col, 0))
        p.setBrush(QBrush(g2))
        p.drawEllipse(QPointF(cx, cy), fw * 0.025, fw * 0.025)

    def _draw_scan(self, p: QPainter, cx, cy, fw, pri):
        sr = fw * 0.44
        a  = min(255, int(self._halo * 1.2))
        p.setPen(QPen(qcol(pri, a), 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        ext   = 60 if self.speaking else 35
        p.drawArc(srect, int(self._scan * 16), int(ext * 16))
        # Second counter scan
        p.setPen(QPen(qcol(C.ACC, a // 3), 1.5))
        p.drawArc(srect, int((-self._scan * 0.7 % 360) * 16), int(ext * 16))

    def _draw_brackets(self, p: QPainter, cx, cy, fw, pri):
        bl = 30
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(qcol(pri, 200), 2))
        for bx, by, dx, dy in [(hl,ht,1,1),(hr,ht,-1,1),(hl,hb,1,-1),(hr,hb,-1,-1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))
        # Crosshair
        gap = fw * 0.13
        p.setPen(QPen(qcol(pri, int(self._halo * 0.6)), 0.8))
        p.drawLine(QPointF(cx - fw*0.52, cy), QPointF(cx - gap, cy))
        p.drawLine(QPointF(cx + gap, cy), QPointF(cx + fw*0.52, cy))
        p.drawLine(QPointF(cx, cy - fw*0.52), QPointF(cx, cy - gap))
        p.drawLine(QPointF(cx, cy + gap), QPointF(cx, cy + fw*0.52))

    def _draw_status(self, p: QPainter, cx, cy, fw, pri):
        sy = cy + fw * 0.42
        if self.muted:
            txt, col = "⊘  MUTED", qcol(C.RED)
        elif self.speaking:
            txt, col = "●  SPEAKING", qcol(C.ACC)
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  THINKING", qcol(C.ACC2)
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  PROCESSING", qcol(C.ACC2)
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  LISTENING", qcol(C.TEAL)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {self.state}", qcol(pri)

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, self.width(), 26), Qt.AlignmentFlag.AlignCenter, txt)


# ---------------------------------------------------------------------------
# Circular gauge widget
# ---------------------------------------------------------------------------
class CircleGauge(QWidget):
    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0
        self._text  = "--"
        self._tick  = 0
        self.setFixedSize(72, 72)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._anim)
        self._tmr.start(50)

    def _anim(self):
        self._tick += 1
        self.update()

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        r = min(W, H) / 2 - 4

        # Background circle
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Track
        p.setPen(QPen(qcol(C.BORDER, 180), 4, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(cx - r + 4, cy - r + 4, (r - 4) * 2, (r - 4) * 2)
        p.drawArc(rect, int(225 * 16), int(-270 * 16))

        # Value arc
        if self._value > 85:
            bar_col = C.RED
        elif self._value > 65:
            bar_col = C.ACC
        else:
            bar_col = self._color

        sweep = int(-270 * self._value / 100)
        if sweep != 0:
            pen = QPen(qcol(bar_col), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, int(225 * 16), sweep * 16)

        # Glow dot at tip
        if self._value > 0:
            tip_ang = math.radians(225 - 270 * self._value / 100)
            tip_r   = r - 4
            tip_x   = cx + tip_r * math.cos(tip_ang)
            tip_y   = cy - tip_r * math.sin(tip_ang)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(bar_col, 220)))
            p.drawEllipse(QPointF(tip_x, tip_y), 3.5, 3.5)

        # Label
        p.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, cy - 20, W, 14),
                   Qt.AlignmentFlag.AlignCenter, self._label)

        # Value text
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(bar_col if self._text != "--" else C.TEXT_DIM), 1))
        p.drawText(QRectF(0, cy - 5, W, 14),
                   Qt.AlignmentFlag.AlignCenter, self._text)


# ---------------------------------------------------------------------------
# Log widget with typewriter effect
# ---------------------------------------------------------------------------
class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)
    _badge_sig = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
                padding: 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 6px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._unread  = 0
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:"):    self._tag = "you"
        elif tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif "err" in tl:              self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(5)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.TEAL),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)


# ---------------------------------------------------------------------------
# File drop zone
# ---------------------------------------------------------------------------
_FILE_ICONS = {
    "image":   ("🖼", C.PRI),    "video":   ("🎬", C.ACC),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", C.RED),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", C.TEAL),
    "code":    ("💻", C.ACC2),   "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", C.PRI),    "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(95)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True
            self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False
        self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True
        self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False
        self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None
        self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for JARVIS", str(Path.home()), "All Files (*.*)")
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 5
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a2e" if z._drag_over else ("#001020" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.TEAL, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  ·  Click to Browse")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 18))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 20, W, 28), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 10, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"
        block_x, block_w = 10, 55
        p.setFont(QFont("Segoe UI Emoji", 20) if _OS == "Windows" else QFont("Arial", 20))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)
        tx = block_x + block_w + 6
        tw = W - tx - 34
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")
        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 32, 0, 26, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 32:
            z.clear_file()
        else:
            z.mousePressEvent(e)


# ---------------------------------------------------------------------------
# Telemetry ticker (footer scrolling text)
# ---------------------------------------------------------------------------
class TelemetryTicker(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self._offset   = 0.0
        self._items    = [
            ("LINK SPEED", "10.3 Gbps"),
            ("NODE STATUS", "OPTIMAL"),
            ("SECURITY LEVEL", "ALPHA"),
            ("SYS TEMP", "--°C"),
            ("UPTIME", "--:--"),
            ("PROTOCOL", "XXXIX"),
            ("AI CORE", "ACTIVE"),
            ("ENCRYPTION", "AES-256"),
        ]
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)
        self._tmr.start(30)

    def update_item(self, key: str, val: str):
        for i, (k, v) in enumerate(self._items):
            if k == key:
                self._items[i] = (k, val)
                return

    def _tick(self):
        self._offset = (self._offset + 0.8) % 9999
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), qcol(C.DARK))
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.drawLine(0, 0, W, 0)

        # Build ticker string
        parts = []
        for k, v in self._items:
            parts.append(f"  ◈  {k}: ")
            parts.append(v)
        full_text = "".join(parts) + "    "

        p.setFont(QFont("Courier New", 8))
        fm    = p.fontMetrics()
        tw    = fm.horizontalAdvance(full_text)
        x     = W - (self._offset % (tw + W))

        while x < W + 20:
            for i in range(0, len(parts), 2):
                label = parts[i]
                value = parts[i+1] if i+1 < len(parts) else ""
                lw = fm.horizontalAdvance(label)
                vw = fm.horizontalAdvance(value)
                p.setPen(QPen(qcol(C.TEXT_DIM), 1))
                p.drawText(int(x), int(H * 0.72), label)
                x += lw
                p.setPen(QPen(qcol(C.PRI), 1))
                p.drawText(int(x), int(H * 0.72), value)
                x += vw
            x += fm.horizontalAdvance("    ")


# ---------------------------------------------------------------------------
# Setup overlay
# ---------------------------------------------------------------------------
class SetupOverlay(QWidget):
    done = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 8, 20, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 8px;
            }}
        """)
        detected = {"darwin": "mac", "windows": "windows"}.get(_OS.lower(), "linux")
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure J.A.R.V.I.S. before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};")
        layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d18; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(8)

        layout.addWidget(_lbl("OPENROUTER API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._or_input = QLineEdit()
        self._or_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._or_input.setPlaceholderText("sk-or-…")
        self._or_input.setFont(QFont("Courier New", 10))
        self._or_input.setFixedHeight(32)
        self._or_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d18; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.ACC2}; }}
        """)
        layout.addWidget(self._or_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};")
        layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.TEAL,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 4px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d18; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 4px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key    = self._key_input.text().strip()
        or_key = self._or_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() + f" QLineEdit {{ border: 1px solid {C.RED}; }}")
            return
        if not or_key:
            self._or_input.setStyleSheet(
                self._or_input.styleSheet() + f" QLineEdit {{ border: 1px solid {C.RED}; }}")
            return
        self.done.emit(key, or_key, self._sel_os)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    _log_sig   = pyqtSignal(str)
    _state_sig = pyqtSignal(str)

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S — MARK XXXIX")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command          = None
        self._muted                   = False
        self._current_file: str | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        body.addWidget(self._build_left_panel(), stretch=0)

        self.hud = HudCanvas(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(self.hud, stretch=5)

        body.addWidget(self._build_right_panel(), stretch=0)
        root.addLayout(body, stretch=1)

        self._ticker = TelemetryTicker()
        root.addWidget(self._ticker)

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        QShortcut(QKeySequence("F4"),  self).activated.connect(self._toggle_mute)
        QShortcut(QKeySequence("F11"), self).activated.connect(self._toggle_fullscreen)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 420
            cw = self.centralWidget()
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()
        cpu = snap["cpu"]
        self._g_cpu.set_value(cpu, f"{cpu:.0f}%")
        mem = snap["mem"]
        self._g_mem.set_value(mem, f"{mem:.0f}%")
        net = snap["net"]
        net_str = f"{net*1024:.0f}KB/s" if net < 1.0 else f"{net:.1f}MB/s"
        self._g_net.set_value(min(100, net * 10), net_str)
        gpu = snap["gpu"]
        self._g_gpu.set_value(gpu if gpu >= 0 else 0, f"{gpu:.0f}%" if gpu >= 0 else "N/A")
        tmp = snap["tmp"]
        self._g_tmp.set_value(
            min(100, (tmp / 100) * 100) if tmp >= 0 else 0,
            f"{tmp:.0f}°C" if tmp >= 0 else "N/A"
        )
        if tmp >= 0:
            self._ticker.update_item("SYS TEMP", f"{tmp:.0f}°C")
        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
            self._ticker.update_item("UPTIME", f"{h:02d}:{m:02d}")
        except Exception:
            pass
        try:
            self._proc_lbl.setText(f"PROC  {len(psutil.pids())}")
        except Exception:
            pass

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(56)
        w.setStyleSheet(f"""
            background: {C.DARK};
            border-bottom: 1px solid {C.BORDER_B};
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _badge(txt, color=C.TEXT_DIM):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_badge("MARK XXXIX", C.PRI_DIM))
        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(1)
        title = QLabel("J.A.R.V.I.S")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Courier New", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        mid.addWidget(title)
        sub = QLabel("Just A Rather Very Intelligent System")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Courier New", 7))
        sub.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        mid.addWidget(sub)
        lay.addLayout(mid)
        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 15, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        hdr = QLabel("◈ SYS MONITOR")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)
        lay.addSpacing(4)

        # Circular gauges in a 2x3 grid
        self._g_cpu = CircleGauge("CPU", C.PRI)
        self._g_mem = CircleGauge("MEM", C.ACC2)
        self._g_net = CircleGauge("NET", C.TEAL)
        self._g_gpu = CircleGauge("GPU", C.ACC)
        self._g_tmp = CircleGauge("TMP", "#ff6688")

        row1 = QHBoxLayout(); row1.setSpacing(4)
        row1.addWidget(self._g_cpu)
        row1.addWidget(self._g_mem)
        lay.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(4)
        row2.addWidget(self._g_net)
        row2.addWidget(self._g_gpu)
        lay.addLayout(row2)

        row3 = QHBoxLayout(); row3.setSpacing(4)
        row3.addWidget(self._g_tmp)
        row3.addStretch()
        lay.addLayout(row3)

        lay.addSpacing(6)

        info_panel = QWidget()
        info_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER_A}; border-radius: 5px;"
        )
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(8, 6, 8, 6)
        ip_lay.setSpacing(3)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.TEAL}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont("Courier New", 8))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)
        lay.addStretch()

        for txt, col in [("AI CORE\nACTIVE", C.TEAL), ("SEC\nCLEARED", C.PRI),
                         ("PROTOCOL\nXXXIX", C.TEXT_DIM)]:
            lbl = QLabel(txt)
            lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {col}; background: {C.PANEL2};"
                f"border: 1px solid {C.BORDER_A}; border-radius: 4px; padding: 5px;"
            )
            lay.addWidget(lbl)

        return w

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        def _sec(txt):
            l = QLabel(f"▸ {txt}")
            l.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            return l

        # Activity log with badge
        log_hdr = QHBoxLayout()
        log_hdr.addWidget(_sec("ACTIVITY LOG"))
        log_hdr.addStretch()
        self._badge_lbl = QLabel("")
        self._badge_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._badge_lbl.setStyleSheet(f"""
            color: white; background: {C.RED};
            border-radius: 7px; padding: 1px 5px;
        """)
        self._badge_lbl.hide()
        log_hdr.addWidget(self._badge_lbl)
        lay.addLayout(log_hdr)

        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_sec("FILE UPLOAD"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("No file loaded — drop or click above to upload")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_sec("COMMAND INPUT"))
        lay.addLayout(self._build_input_row())

        self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(32)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
        fs_btn.setFixedHeight(24)
        fs_btn.setFont(QFont("Courier New", 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border: 1px solid {C.BORDER_B}; }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        return w

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(32)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d18; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 3px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(32, 32)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell JARVIS what to do")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇  MICROPHONE MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #1a000a; color: {C.RED};
                    border: 1px solid {C.RED}; border-radius: 4px;
                }}
            """)
        else:
            self._mute_btn.setText("🎙  MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a10; color: {C.TEAL};
                    border: 1px solid {C.TEAL}; border-radius: 4px;
                }}
                QPushButton:hover {{ background: #002518; }}
            """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt:
            return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")

    def _check_config(self) -> bool:
        if not API_FILE.exists():
            return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return (bool(d.get("gemini_api_key")) and
                    bool(d.get("openrouter_api_key")) and
                    bool(d.get("os_system")))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 420
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, or_key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({
                "gemini_api_key":    key,
                "openrouter_api_key": or_key,
                "os_system":         os_name,
            }, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. JARVIS online.")


# ---------------------------------------------------------------------------
# Public API shim — identical interface to old JarvisUI
# ---------------------------------------------------------------------------
class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app

    def mainloop(self):
        self._app.exec()

    def protocol(self, *_):
        pass


class JarvisUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")