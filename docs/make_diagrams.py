"""make_diagrams.py - draws the three LOCK diagrams (SVG and PNG).
1. lock-system.*  : the Gigatron as LOCK uses it
2. lock-module.*  : wiring of the plug-in switch and light module
3. lock-fascia.*  : the front panel of the module, to scale (1 unit = 1 mm)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle

INK = "#1c1c1c"
RED, GREEN, YEL, PUR, GREY = "#f2b8b0", "#bfe3b4", "#f7e3a1", "#d9c3e8", "#e3e3e3"

def box(ax, x, y, w, h, text, color, size=10, weight="normal", dash=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                 fc=color, ec=INK, lw=1.2, ls="--" if dash else "-"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=INK, weight=weight)

def arrow(ax, a, b, both=False, label=None, off=(0, 0.12), size=8):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="<->" if both else "->", color=INK, lw=1.3))
    if label:
        ax.text((a[0] + b[0]) / 2 + off[0], (a[1] + b[1]) / 2 + off[1], label, ha="center", va="center", fontsize=size, color=INK)

def line(ax, pts, **kw):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=kw.get("c", INK), lw=kw.get("lw", 1.3), solid_capstyle="round")

def canvas(w, h, title):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.axis("off")
    ax.text(0.2, h - 0.35, title, fontsize=14, weight="bold", color=INK)
    return fig, ax

def save(fig, name):
    for ext in ("svg", "png"):
        fig.savefig(f"{name}.{ext}", dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)

# ---------------------------------------------------------------- 1. system
fig, ax = canvas(13.8, 8.6, "LOCK SYSTEM DIAGRAM  (Gigatron board + plug-in module)")
box(ax, 0.4, 6.4, 2.4, 1.0, "Clock\n6.25 MHz crystal", GREEN)
box(ax, 0.4, 3.9, 2.4, 1.6, "PROGRAM CHIP\n27C1024, 64K x 16 bit\nholds lock.rom\n(read only)", RED, weight="bold")
box(ax, 0.4, 1.6, 2.4, 1.4, "RAM 32K\n62256\nworking memory,\nwiped before results", RED)
box(ax, 3.9, 2.6, 3.2, 3.6, "GIGATRON CPU\n\nabout 30 logic chips\ncontrol unit, adder,\nAC, X, Y, program counter\n\nno microprocessor", RED, size=11, weight="bold")
box(ax, 8.2, 6.4, 2.2, 1.0, "OUT register\n8 bits", YEL)
box(ax, 8.2, 4.5, 2.2, 1.0, "Input register\n74HC595, 8 bits", YEL)
box(ax, 8.2, 2.6, 2.2, 1.0, "Extended output\nregister", YEL)
box(ax, 10.9, 7.3, 1.6, 0.8, "VGA socket\nnot used", GREY, dash=True, size=9)
box(ax, 10.9, 2.6, 1.6, 1.0, "4 board LEDs\nand sound\nnot used", GREY, dash=True, size=9)
box(ax, 10.9, 4.5, 2.6, 2.3, "CONTROLLER\nPORT\n9-pin\n\n2 Data in\n3 Latch out\n4 Pulse out\n6 +5 V   8 0 V", PUR, size=9, weight="bold")
box(ax, 3.9, 0.4, 3.2, 1.0, "Power in: 5 V, mini-USB\n(power only, no data lines)", GREEN, size=9)
box(ax, 8.2, 0.4, 5.3, 1.5, "LOCK MODULE (plugs into the port)\n11 switches, STORE, BACK, NEXT\n11 data lights + 12 status lights", PUR, weight="bold")
arrow(ax, (1.6, 6.4), (3.9, 5.9))
arrow(ax, (2.8, 4.7), (3.9, 4.7), label="instructions")
arrow(ax, (2.8, 2.9), (3.9, 3.3), both=True, label="data", off=(0, 0.25))
arrow(ax, (7.1, 5.6), (8.2, 6.7))
arrow(ax, (8.2, 5.0), (7.1, 4.6))
arrow(ax, (7.1, 3.6), (8.2, 3.1))
arrow(ax, (10.4, 7.1), (10.9, 7.6))
arrow(ax, (10.4, 6.7), (10.9, 6.2), label="bits 7, 6", off=(0.55, 0.12), size=7)
arrow(ax, (10.9, 5.0), (10.4, 5.0))
arrow(ax, (10.4, 3.1), (10.9, 3.1))
arrow(ax, (13.0, 4.5), (13.0, 1.9), both=True, label="cable", off=(0.35, 0))
arrow(ax, (5.5, 1.4), (5.5, 2.6))
ax.text(0.4, 0.35, "Nothing else is connected.\nNo network, no storage,\nno USB data.", fontsize=9, color=INK, va="bottom")
save(fig, "lock-system")

# ---------------------------------------------------------------- 2. module
fig, ax = canvas(14, 9.9, "LOCK MODULE WIRING  (one cable to the controller port)")
box(ax, 0.3, 2.6, 1.7, 4.6, "", PUR)
ax.text(1.15, 6.9, "PORT\n9-pin", ha="center", va="center", fontsize=10, weight="bold")
pins = {"6  +5 V": 6.1, "2  DATA": 5.3, "3  LATCH": 4.5, "4  PULSE": 3.7, "8  0 V": 2.9}
for t, y in pins.items():
    ax.text(1.15, y, t, ha="center", va="center", fontsize=9)
Y5, YD, YL, YP, Y0 = 6.1, 5.3, 4.5, 3.7, 2.9
# inputs
box(ax, 4.0, 6.6, 2.3, 1.3, "74HC165  (A)\nH..A = word bits 7..0", YEL, size=9)
box(ax, 7.4, 6.6, 2.6, 1.3, "74HC165  (B)\nH = STORE  G = NEXT  F = BACK\nE,D = +5 V\nC,B,A = bits 10,9,8", YEL, size=8)
box(ax, 4.0, 8.2, 6.0, 0.7, "11 switches + 3 buttons to 0 V, each with a 10k pull-up to +5 V", GREEN, size=9)
arrow(ax, (5.15, 8.2), (5.15, 7.9)); arrow(ax, (8.7, 8.2), (8.7, 7.9))
arrow(ax, (7.4, 7.25), (6.3, 7.25), label="QH to SER", off=(0, 0.17), size=7)
ax.text(10.15, 7.25, "SER = +5 V", fontsize=7, va="center")
line(ax, [(4.0, 7.25), (3.0, 7.25), (3.0, YD), (2.0, YD)])           # QH(A) -> DATA
ax.text(3.05, 7.4, "QH", fontsize=7)
# lights
xs = [4.2 + i * 3.4 for i in range(3)]
use = ["count 1-32, mode B, mode A", "spare, blocks D C B A,\ndata lights 11 10 9", "data lights 8 to 1"]
for i, x in enumerate(xs):
    box(ax, x, 1.4, 1.15, 1.0, f"74HC595\n#{i + 1}", YEL, size=8)
    ax.text(x + 0.75, 1.15, "QA..QH: " + use[i], fontsize=7, va="center")
    if i: arrow(ax, (xs[i - 1] + 1.15, 1.9), (x, 1.9))
    arrow(ax, (x + 0.575, 1.4), (x + 0.575, 0.95))
box(ax, 3.6, 0.2, 10.0, 0.75, "24 outputs: each used one drives an LED through its own resistor to 0 V  (11 data, 4 block, 6 count, 2 mode, 1 spare)", GREEN, size=9)
ax.text(2.55, 2.0, "SER in", fontsize=7); ax.text(xs[1] - 0.28, 2.02, "QH'", fontsize=7)
# buses
line(ax, [(2.0, YL), (13.4, YL)]); ax.text(13.45, YL, "LATCH", fontsize=8, va="center")
line(ax, [(2.0, YP), (13.4, YP)]); ax.text(13.45, YP, "PULSE", fontsize=8, va="center")
for x in (4.6, 8.0):                                                    # 165: SH/LD and CLK
    line(ax, [(x, YL), (x, 6.6)]); ax.plot(x, YL, "o", c=INK, ms=4)
    line(ax, [(x + 0.9, YP), (x + 0.9, 6.6)]); ax.plot(x + 0.9, YP, "o", c=INK, ms=4)
ax.text(4.63, 6.35, "SH/LD", fontsize=7); ax.text(5.53, 6.35, "CLK", fontsize=7)
line(ax, [(3.3, YL), (3.3, 1.9), (xs[0], 1.9)]); ax.plot(3.3, YL, "o", c=INK, ms=4)   # LATCH -> SER of #1
for x in xs:
    line(ax, [(x + 0.3, YL), (x + 0.3, 2.4)]); ax.plot(x + 0.3, YL, "o", c=INK, ms=4)
    line(ax, [(x + 0.85, YP), (x + 0.85, 2.4)]); ax.plot(x + 0.85, YP, "o", c=INK, ms=4)
ax.text(xs[2] + 0.36, 2.5, "RCLK", fontsize=7); ax.text(xs[2] + 0.92, 2.5, "SRCLK", fontsize=7)
ax.text(10.6, 6.0, "Not drawn: +5 V and 0 V to every chip,\na 100 nF capacitor at each chip,\n165 clock-inhibit to 0 V,\n595 OE to 0 V and SRCLR to +5 V.", fontsize=8, va="top")
ax.text(2.1, Y5 + 0.12, "to all chips", fontsize=7); ax.text(2.1, Y0 + 0.12, "to all chips", fontsize=7)
line(ax, [(2.0, Y5), (2.8, Y5)]); line(ax, [(2.0, Y0), (2.8, Y0)])
save(fig, "lock-module")

# ---------------------------------------------------------------- 3. fascia
W, H = 250, 124
fig, ax = plt.subplots(figsize=(W / 18, H / 18))
ax.set_xlim(-4, W + 4); ax.set_ylim(-14, H + 4); ax.set_aspect("equal"); ax.axis("off")
ax.add_patch(FancyBboxPatch((0, 0), W, H, boxstyle="round,pad=0,rounding_size=4", fc="#f4f1ea", ec=INK, lw=1.6))
for x, y in ((6, 6), (W - 6, 6), (6, H - 6), (W - 6, H - 6)):
    ax.add_patch(Circle((x, y), 1.6, fc="white", ec=INK, lw=0.8))
def led(x, y, r=2.5): ax.add_patch(Circle((x, y), r, fc="#ffd9d2", ec=INK, lw=1.0))
def label(x, y, t, size=6.5, **kw): ax.text(x, y, t, ha=kw.pop("ha", "center"), va="center", fontsize=size, color=INK, **kw)
def toggle(x, y):
    ax.add_patch(Circle((x, y), 4.2, fc="#dcdcdc", ec=INK, lw=1.0))
    ax.add_patch(Rectangle((x - 1.2, y), 2.4, 7.5, fc="#9a9a9a", ec=INK, lw=0.8))
def button(x, y, name):
    ax.add_patch(Circle((x, y), 5.5, fc="#dcdcdc", ec=INK, lw=1.0)); ax.add_patch(Circle((x, y), 3.6, fc="#b9b9b9", ec=INK, lw=0.8))
    label(x, y - 9.5, name, 8, weight="bold")
label(14, 112, "LOCK", 17, weight="bold", ha="left"); label(46, 111.2, "key calculator", 8, ha="left")
X = [22 + 15 * i for i in range(11)]
label(X[0] - 13, 99, "value", 5.5, ha="left"); label(X[0] - 13, 80.5, "light", 5.5, ha="left")
for i, x in enumerate(X):
    label(x, 99, str(1 << (10 - i)), 7)
    led(x, 88); label(x, 80.5, str(i + 1), 5.5)
    toggle(x, 56); label(x - 7.2, 62.5, "1", 5.5); label(x - 7.2, 51, "0", 5.5)
ax.plot([X[7] + 7.5] * 2, [79, 94], color=INK, lw=0.8, ls="--"); label(X[7] + 8.5, 76, "block D ends", 5.5, ha="left")
ax.plot([X[4] - 6, X[4] - 6, X[10] + 6, X[10] + 6], [45, 42, 42, 45], color=INK, lw=0.9)
label((X[4] + X[10]) / 2, 38.5, "COIN FLIPS  (entry 12)", 6.5)
ax.plot([X[0] - 6, X[0] - 6, X[10] + 6, X[10] + 6], [70, 67.5, 67.5, 70], color=INK, lw=0.9); label(X[5], 73, "WORD  (entries 1 to 11)", 6.5)
button(X[5], 22, "STORE")
ax.plot([186, 186], [10, 114], color=INK, lw=0.8, ls=":")
label(218, 112, "BLOCK", 7.5, weight="bold")
for j, (name, rng) in enumerate((("A", "1-11"), ("B", "12-22"), ("C", "23-33"), ("D", "34-41"))):
    x = 197 + 14 * j; label(x, 105.5, name, 7); led(x, 99); label(x, 93.5, rng, 5.5)
label(218, 85, "ROW  /  COUNT", 7.5, weight="bold")
for j in range(6):
    x = 195.5 + 9 * j; label(x, 79.5, str(32 >> j), 6.5); led(x, 73, 2.2)
label(218, 62, "MODE", 7.5, weight="bold")
led(197, 53, 2.2); led(205, 53, 2.2)
for j, (p, t) in enumerate((("o  o", "enter"), ("o  \u25cf", "busy"), ("\u25cf  o", "12th word"), ("\u25cf  \u25cf", "QR row"))):
    label(214, 57.5 - 4.2 * j, p, 6, ha="left"); label(224, 57.5 - 4.2 * j, t, 6, ha="left")
button(204, 22, "BACK"); button(232, 22, "NEXT")
label(W / 2, -7, "Front panel of the LOCK module, proposed layout. 250 x 124 mm, switch and light spacing 15 mm. Cable leaves from the back edge.", 7)
for ext in ("svg", "png"):
    fig.savefig(f"lock-fascia.{ext}", dpi=170, bbox_inches="tight", facecolor="white")
plt.close(fig)
