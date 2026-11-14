"""Command-line interface: evaluate an ownership graph against OFAC's 50 Percent Rule.

Usage:
    python3 -m ofac50 INPUT.json [--format text|json] [--compare-naive]

Input JSON:
    {
      "blocked_persons": [{"name": "X", "program": "SDGT", "status": "blocked"}],
      "stakes": [{"owner": "X", "entity": "A", "pct": 50, "source": "FAQ 401 ex. 1"}]
    }

A stake with "pct": null records a holding whose size is unknown; the
engine reports lower and upper bounds instead of guessing.

Exit codes: 0 = evaluated cleanly; 2 = input rejected (see stderr).
"""

import argparse
import json
import sys

from .engine import InputError, Seed, Stake, evaluate


def load(path: str):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    seeds = [Seed(name=s["name"], program=s.get("program", "unspecified"),
                  status=s.get("status", "blocked"))
             for s in doc.get("blocked_persons", [])]
    stakes = [Stake(owner=s["owner"], entity=s["entity"], pct=s.get("pct"),
                    source=s.get("source", ""))
              for s in doc.get("stakes", [])]
    return seeds, stakes


def render_text(results: dict) -> str:
    lines = []
    for name, r in results.items():
        head = f"{name}: {r.status.upper()}"
        if r.is_seed:
            lines.append(head)
        elif r.status == "blocked":
            lines.append(f"{head} (aggregate {r.aggregate_pct:.4g}%)")
        elif r.status == "indeterminate":
            if r.upper_pct > r.aggregate_pct:
                lines.append(f"{head} (known {r.aggregate_pct:.4g}%, up to {r.upper_pct:.4g}%)")
            else:
                lines.append(f"{head} (aggregate {r.aggregate_pct:.4g}%)")
        else:
            lines.append(f"{head} (aggregate {r.aggregate_pct:.4g}%)")
        for reason in r.reasons:
            lines.append(f"    - {reason}")
        if r.contributors:
            lines.append("    chain: " + ", ".join(
                f"{o} holds {p:.4g}%" + (f" [{src}]" if src else "")
                for (o, p, src) in r.contributors))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ofac50", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="ownership graph JSON")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--compare-naive", action="store_true",
                    help="also compute path-product effective ownership and flag disagreements")
    args = ap.parse_args(argv)

    try:
        seeds, stakes = load(args.input)
        results = evaluate(seeds, stakes, compare_naive=args.compare_naive)
    except InputError as exc:
        print(f"input rejected: {exc}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"could not parse input: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        out = {name: {k: v for k, v in r.__dict__.items() if k != "name"}
               for name, r in results.items()}
        print(json.dumps(out, indent=2))
    else:
        print(render_text(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
