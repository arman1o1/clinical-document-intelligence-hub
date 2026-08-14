"""Generate the architecture / data-flow diagram.

    python assets/make_diagram.py           -> architecture.png       (README: titled)
    python assets/make_diagram.py --bare    -> architecture_bare.png  (deck: no title,
                                               the slide already carries one)
"""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from pathlib import Path

INK, MUTED = "#1c2733", "#5b6b7c"
BLUE, TEAL, AMBER, RED, GREEN, GREY = "#1b6ca8", "#12786e", "#c26401", "#b3261e", "#3d6b47", "#8593a3"

BARE = "--bare" in sys.argv
TOP = 62 if BARE else 72          # drop the header band when the slide supplies it
BOT = 2.2 if BARE else 0

fig, ax = plt.subplots(figsize=(13.6, 6.2 if BARE else 7.2), dpi=200)
ax.set_xlim(0, 136); ax.set_ylim(BOT, TOP); ax.axis("off")


def box(x, y, w, h, title, lines=(), fc="#ffffff", ec=BLUE, ts=10.5, ss=8.3):
    """Title sits at a fixed offset from the TOP edge; body flows beneath it."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.7,rounding_size=2.0",
                                fc=fc, ec=ec, lw=1.8, zorder=2))
    n = len(title.split("\n"))
    ty = y + h - 3.4 - (n - 1) * 2.4
    ax.text(x + w / 2, ty, title, ha="center", va="center", fontsize=ts,
            color=INK, weight="bold", zorder=3, linespacing=1.3)
    if lines:
        # anchored to the top rather than centred: body length then cannot push
        # the last line through the bottom border
        ax.text(x + w / 2, ty - 3.4, "\n".join(lines), ha="center",
                va="top", fontsize=ss, color=MUTED, zorder=3, linespacing=1.65)


def arrow(x1, y1, x2, y2, color=BLUE, lw=1.9, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", lw=lw, color=color,
                                 linestyle=ls, mutation_scale=15, zorder=1,
                                 connectionstyle=f"arc3,rad={rad}"))


def label(x, y, t, color=MUTED, size=7.9):
    ax.text(x, y, t, ha="center", va="center", fontsize=size, color=color, style="italic",
            zorder=4, linespacing=1.35,
            path_effects=[pe.withStroke(linewidth=3.5, foreground="white")])


if not BARE:
    ax.text(2.5, 68.4, "Clinical Document Intelligence Hub", fontsize=15.5,
            weight="bold", color=INK)
    ax.text(2.5, 64.6, "document  →  verified structured record  →  triaged action",
            fontsize=10.3, color=MUTED, style="italic")

# ---------------- row 1 : ingest and extract ----------------
box(2.5, 39, 22, 20, "Clinical\ndocuments",
    ["intake · discharge", "labs · physician notes", "", "(txt / PDF)"], ec=GREY, fc="#f6f8fa")
box(29, 39, 24, 20, "Schema-constrained\nextraction",
    ["Claude, via tool use.", "", "The schema forces one", "(value, evidence) pair", "per field. No value", "without a citation."],
    ec=BLUE, fc="#eef5fb", ss=8.1)
box(57.5, 39, 26, 20, "Verification layer",
    ["g   quote grounded in doc", "d   value present in doc", "v   value supported by quote", "a   agreement across k runs", "", "+  per-item list filtering"],
    ec=TEAL, fc="#e9f5f3", ss=8.1)
box(88, 39, 22, 20, "Human review\nqueue",
    ["fields that fail", "the gate are", "withheld, never", "shown as though", "they were verified"], ec=AMBER, fc="#fdf3e7")

# ---------------- row 2 : verified record ----------------
box(57.5, 22, 26, 12.5, "Verified PatientRecord",
    ["typed fields · per-field", "confidence · provenance"], ec=TEAL, fc="#e9f5f3")

# ---------------- row 3 : reasoning and output ----------------
box(2.5, 3, 26, 15.5, "Clinical rules engine",
    ["lab thresholds · med safety", "allergy conflicts · care gaps", "", "deterministic and auditable"], ec=RED, fc="#fbeeed")
box(33, 3, 24, 15.5, "Triage & routing",
    ["urgency score 0–100", "IMMEDIATE / PHARMACY /", "COORDINATION / ROUTINE"], ec=RED, fc="#fbeeed")
box(61.5, 3, 26, 15.5, "Summary card",
    ["structured fields, flags,", "rationale, next step", "", "for clinical + admin staff"], ec=GREEN, fc="#eef5ef")

# ---------------- eval sidecar ----------------
box(114, 14, 20, 44, "Evaluation\nharness",
    ["32 documents", "with exact", "gold labels", "", "fault injection", "at a known rate", "", "headline metric:", "silent-error rate", "", "no API key", "required"],
    ec=MUTED, fc="#f4f6f8", ts=10.2, ss=8.0)

# ---------------- arrows ----------------
arrow(24.5, 49, 29, 49, GREY)
arrow(53, 49, 57.5, 49, BLUE)
arrow(83.5, 49, 88, 49, AMBER)

arrow(70.5, 39, 70.5, 34.5, TEAL)
label(77.0, 36.9, "passes", TEAL)

arrow(57.5, 27, 28.5, 20, RED, rad=-0.10)
label(43, 26.2, "verified fields only", RED)
arrow(28.5, 10.7, 33, 10.7, RED)
arrow(57, 10.7, 61.5, 10.7, GREEN)

arrow(110, 46, 114, 44, MUTED, ls=(0, (3, 2)), lw=1.4)
arrow(114, 26, 87.5, 14.5, MUTED, ls=(0, (3, 2)), lw=1.4, rad=0.10)

if not BARE:
    ax.text(2.5, 0.2,
            "The LLM extracts. Rules decide. Nothing reaches the summary card without a verified source span.",
            fontsize=9.6, color=INK, style="italic", weight="bold")

out = Path(__file__).parent / ("architecture_bare.png" if BARE else "architecture.png")
plt.savefig(out, bbox_inches="tight", facecolor="white", pad_inches=0.28)
print("wrote", out)
