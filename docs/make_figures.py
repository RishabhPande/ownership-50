"""Regenerate the README diagrams. Deterministic, zero third-party deps beyond matplotlib.

    python3 docs/make_figures.py

Statuses: blocked = red, not blocked = grey, indeterminate = amber.
"""

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "path"
import matplotlib.pyplot as plt

BLOCKED = "#d64545"
CLEAR = "#9aa3ad"
UNKNOWN = "#e0a458"
EDGE = "#4a4f55"


def draw(name, nodes, edges, title, caption):
    fig, ax = plt.subplots(figsize=(5.6, 3.4), dpi=100)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    for (o, e, label, dashed) in edges:
        x1, y1 = nodes[o][:2]
        x2, y2 = nodes[e][:2]
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=EDGE, lw=1.4,
                                    linestyle="--" if dashed else "-",
                                    shrinkA=26, shrinkB=26))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + 0.12, my + 0.18, label, fontsize=9, color=EDGE,
                ha="center", style="italic" if dashed else "normal")
    for _, (x, y, label, status) in nodes.items():
        color = {"blocked": BLOCKED, "clear": CLEAR, "unknown": UNKNOWN}[status]
        ax.add_patch(plt.Circle((x, y), 0.52, color=color, zorder=3))
        ax.text(x, y, label, fontsize=11, color="white", ha="center",
                va="center", zorder=4, fontweight="bold")
    ax.set_title(title, fontsize=11, loc="left", pad=10)
    fig.text(0.02, 0.02, caption, fontsize=8, color="#666")
    fig.savefig(f"docs/img/{name}.svg", bbox_inches="tight")
    plt.close(fig)


draw("faq401_ex1",
     {"X": (2, 4.6, "X", "blocked"), "A": (5, 2.9, "A", "blocked"),
      "B": (8, 1.2, "B", "blocked")},
     [("X", "A", "50%", False), ("A", "B", "50%", False)],
     "FAQ 401, example 1: a blocked owner's stake counts in full",
     "X blocks A; A is now a blocked person, so its 50% of B counts at face value and B is blocked. A path product would show 25%.")

draw("faq401_ex2",
     {"X": (1.6, 2.9, "X", "blocked"), "A": (5, 4.6, "A", "blocked"),
      "B": (5, 1.2, "B", "blocked"), "C": (8.4, 2.9, "C", "blocked")},
     [("X", "A", "50%", False), ("X", "B", "50%", False),
      ("A", "C", "25%", False), ("B", "C", "25%", False)],
     "FAQ 401, example 2: two blocked channels aggregate",
     "C is owned 25% + 25% by blocked persons: 50% in the aggregate. A path product would show 25%.")

draw("faq401_ex4",
     {"X": (1.6, 2.9, "X", "blocked"), "A": (5, 4.6, "A", "blocked"),
      "B": (5, 1.2, "B", "clear"), "C": (8.4, 2.9, "C", "clear")},
     [("X", "A", "50%", False), ("X", "B", "25%", False),
      ("A", "C", "25%", False), ("B", "C", "25%", False)],
     "FAQ 401, example 4: only A is blocked",
     "B is not blocked, so its 25% of C counts for nothing. C's aggregate from blocked owners is 25%.")

draw("cycle_crossholdings",
     {"X": (1.6, 2.9, "X", "blocked"), "A": (5.4, 4.4, "A", "unknown"),
      "B": (5.4, 1.4, "B", "unknown")},
     [("X", "A", "20%", False), ("X", "B", "20%", False),
      ("A", "B", "30%", False), ("B", "A", "30%", False)],
     "Circular ownership: the guidance is silent",
     "Build up from X: neither clears 50%. Assume both blocked: they hold each other up. The engine flags the disagreement.")

draw("unknown_stakes",
     {"X": (2.2, 4.4, "X", "blocked"), "Y": (2.2, 1.4, "Y", "blocked"),
      "A": (7.4, 2.9, "A", "unknown")},
     [("X", "A", "40%", False), ("Y", "A", "?", True)],
     "Unknown is not 'not blocked'",
     "Known stakes from blocked persons: 40%. The unknown holding could push A over 50%: indeterminate, not a clean pass.")

print("wrote 5 figures")
