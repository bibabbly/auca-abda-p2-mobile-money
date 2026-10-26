"""Draw the report diagrams: PostgreSQL schema, graph schema, the set A cycle and an
ownership/device network for set A. Saves PNGs to reports/figures/.

Usage:  .venv\\Scripts\\python.exe reports\\diagrams.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent / "figures"
BLUE, RED, GREEN, GREY, INK = "#3b6ea5", "#c0504d", "#4f8a4b", "#888888", "#222222"


def box(ax, x, y, w, h, title, lines, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02", fc="white", ec=color, lw=1.8))
    ax.add_patch(FancyBboxPatch((x, y + h - 0.55), w, 0.55, boxstyle="round,pad=0.02", fc=color, ec=color))
    ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="center", color="white", fontsize=11, weight="bold")
    for i, ln in enumerate(lines):
        ax.text(x + 0.12, y + h - 0.85 - i * 0.38, ln, ha="left", va="center", fontsize=8.6, family="monospace",
                color=INK)


def arrow(ax, p, q, label="", color=INK, rad=0.0, fs=8.5, offset=(0, 0.15)):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=14, lw=1.4, color=color,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=4, shrinkB=4))
    if label:
        ax.text((p[0] + q[0]) / 2 + offset[0], (p[1] + q[1]) / 2 + offset[1], label, ha="center", va="bottom",
                fontsize=fs, color=color, bbox=dict(fc="white", ec="none", pad=1))


def pg_schema():
    fig, ax = plt.subplots(figsize=(11, 6.2))
    box(ax, 0.2, 3.6, 3.0, 1.75, "customers", ["PK customer_id  INTEGER", "   region       TEXT"], BLUE)
    box(ax, 4.2, 3.2, 3.3, 2.15, "accounts", ["PK account_id   INTEGER", "FK customer_id  INTEGER", "   role         TEXT"],
        BLUE)
    box(ax, 0.2, 0.3, 3.0, 1.75, "devices", ["PK device_id    INTEGER", "   access_type  TEXT"], BLUE)
    box(ax, 4.0, -0.4, 3.7, 3.1, "account_devices",
        ["PK,FK account_id  INTEGER", "PK,FK device_id   INTEGER", "   first_day  SMALLINT", "   last_day   SMALLINT",
         "   observations INTEGER", "CHECK 0<=first<=last<=29"], BLUE)
    box(ax, 8.4, 2.4, 3.4, 2.95, "transfers",
        ["PK transfer_id  BIGINT", "FK sender_id    INTEGER", "FK receiver_id  INTEGER", "   occurred_at  BIGINT",
         "   amount_rwf   INTEGER", "CHECK amount_rwf > 0"], BLUE)
    arrow(ax, (4.2, 4.5), (3.2, 4.5), "customer_id", rad=0, offset=(0, -0.45))
    arrow(ax, (5.85, 2.7), (5.85, 3.2), "account_id", offset=(0.55, -0.12))
    arrow(ax, (4.0, 1.2), (3.2, 1.2), "device_id", offset=(0, 0.05))
    arrow(ax, (8.4, 4.6), (7.5, 4.6), "sender_id", offset=(0, 0.05))
    arrow(ax, (8.4, 3.0), (7.5, 3.6), "receiver_id", offset=(0, -0.4))
    ax.text(6.0, 5.75, "Arrows point from the foreign key to the referenced primary key. All columns NOT NULL.",
            ha="center", fontsize=9.5, color=GREY)
    ax.set_xlim(0, 12); ax.set_ylim(-0.6, 6); ax.axis("off")
    save(fig, "pg_schema.png")


def node(ax, x, y, text, color, r=0.75, fs=9):
    ax.add_patch(plt.Circle((x, y), r, fc="white", ec=color, lw=2))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, color=INK)


def neo_schema():
    fig, ax = plt.subplots(figsize=(11, 5))
    node(ax, 1.5, 2.5, ":Customer\ncustomer_id\nregion", GREEN, r=1.05)
    node(ax, 6.0, 2.5, ":Account\naccount_id\nrole", BLUE, r=1.05)
    node(ax, 10.5, 2.5, ":Device\ndevice_id\naccess_type", RED, r=1.05)
    arrow(ax, (2.55, 2.5), (4.95, 2.5), ":OWNS", color=GREEN)
    arrow(ax, (7.05, 2.5), (9.45, 2.5), ":USED_DEVICE\nfirst_day, last_day, observations", color=RED, fs=8.5)
    ax.add_patch(FancyArrowPatch((5.4, 3.4), (6.6, 3.4), arrowstyle="-|>", mutation_scale=14, lw=1.4, color=BLUE,
                                 connectionstyle="arc3,rad=-1.6"))
    ax.text(6.0, 4.85, ":TRANSFER  transfer_id, occurred_at, amount_rwf\n(one relationship per payment)",
            ha="center", fontsize=8.8, color=BLUE)
    ax.text(6.0, 0.6, "Integer ID groups Customer / Account / Device keep the three ID spaces separate.",
            ha="center", fontsize=9.5, color=GREY)
    ax.set_xlim(0, 12); ax.set_ylim(0.2, 5.6); ax.set_aspect("equal"); ax.axis("off")
    save(fig, "neo_schema.png")


def cycle_a():
    fig, ax = plt.subplots(figsize=(10, 6.5))
    pos = {998: (2, 5), 8917: (8, 5), 16836: (8, 1), 24755: (2, 1)}
    for acc, (x, y) in pos.items():
        node(ax, x, y, f"Account\n{acc}\nperson", RED if acc == 998 else BLUE, r=0.8)
    steps = [(998, 8917, "20000001\n10:00:00  200,000 RWF"),
             (8917, 16836, "20000002\n10:00:40  196,000 RWF (98%)"),
             (16836, 24755, "20000003\n10:01:20  192,080 RWF (98%)"),
             (24755, 998, "20000004\n10:02:00  188,238 RWF (98%)")]
    for a, b, label in steps:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=16, lw=1.8, color=INK,
                                     shrinkA=30, shrinkB=30))
        ax.text((x1 + x2) / 2, (y1 + y2) / 2, label, ha="center", va="center", fontsize=9,
                bbox=dict(fc="#fff8e6", ec="#e0c080", pad=3))
    ax.text(5, 6.3, "Q6 cycle, set A, 6 September 2026 CAT: 4 transfers in 120 s, back to account 998",
            ha="center", fontsize=11, weight="bold")
    ax.text(5, -0.3, "All four accounts were also observed on handset 228001 for days 0-29 (Q3).",
            ha="center", fontsize=9.5, color=GREY)
    ax.set_xlim(0, 10); ax.set_ylim(-0.6, 6.7); ax.set_aspect("equal"); ax.axis("off")
    save(fig, "cycle_A.png")


def network_a():
    fig, ax = plt.subplots(figsize=(11, 6))
    nodes = {
        "A998": (1.2, 3.0, "Account\n998\n(review)", RED),
        "D228001": (4.0, 4.6, "Device\n228001\nhandset", GREY),
        "D998": (4.0, 1.4, "Device\n998\nhandset", GREY),
        "A8917": (7.0, 5.6, "Account\n8917", BLUE),
        "A16836": (7.0, 4.0, "Account\n16836", BLUE),
        "A24755": (7.0, 2.4, "Account\n24755", BLUE),
        "A220998": (7.0, 0.6, "Account\n220998", BLUE),
        "C16836": (9.6, 4.0, "Customer\n16836", GREEN),
        "A236836": (12.0, 4.0, "Account\n236836", BLUE),
        "C998": (1.2, 0.3, "Customer\n998", GREEN),
    }
    edges = [("A998", "D228001", "USED_DEVICE"), ("A8917", "D228001", "USED_DEVICE"),
             ("A16836", "D228001", "USED_DEVICE"), ("A24755", "D228001", "USED_DEVICE"),
             ("A998", "D998", "USED_DEVICE"), ("A220998", "D998", "USED_DEVICE"),
             ("C16836", "A16836", "OWNS"), ("C16836", "A236836", "OWNS"),
             ("C998", "A998", "OWNS"), ("C998", "A220998", "OWNS")]
    for a, b, label in edges:
        (x1, y1), (x2, y2) = nodes[a][:2], nodes[b][:2]
        color = GREEN if label == "OWNS" else RED
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12, lw=1.3, color=color,
                                     shrinkA=26, shrinkB=26))
    for x, y, text, color in nodes.values():
        node(ax, x, y, text, color, r=0.62, fs=8)
    ax.text(6.6, 6.6, "Q4 set A: ownership and device links (1-4 links from account 998)",
            ha="center", fontsize=11, weight="bold")
    ax.text(6.6, -0.65, "4-link path: Account 998 - Device 228001 - Account 16836 - Customer 16836 - Account 236836.  "
                        "220998 is a second wallet of customer 998.", ha="center", fontsize=9, color=GREY)
    ax.text(0.2, 6.1, "green = OWNS, red = USED_DEVICE", fontsize=8.5, color=GREY)
    ax.set_xlim(0, 13); ax.set_ylim(-0.9, 6.9); ax.set_aspect("equal"); ax.axis("off")
    save(fig, "network_A.png")


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print("saved", OUT / name)


if __name__ == "__main__":
    pg_schema(); neo_schema(); cycle_a(); network_a()
