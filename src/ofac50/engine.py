"""OFAC 50 Percent Rule reference engine.

A testing and teaching aid. This is NOT a compliance tool and makes no
compliance determination. See README.md for scope and limits.

Semantics (derived from OFAC's revised 50 Percent Rule guidance of
13 August 2014 and FAQs 398-402, ofac.treasury.gov/faqs/topic/1521):

* A person blocked under an OFAC program is a "blocked person" seed.
* An entity is blocked if it is owned 50 percent or more IN THE AGGREGATE
  by one or more blocked persons (FAQ 399). Stakes of persons blocked
  under different programs are aggregated.
* Once an entity is blocked, it is itself a blocked person, and any
  stake IT holds counts IN FULL toward other entities (FAQ 401). There is
  no multiplication along a path: a blocked owner's stake counts at face
  value.
* This is a monotone build-up from the seeds to a least fixed point.

What this module refuses to hide:

* Unknown stakes. If missing data could flip an answer, the status is
  "indeterminate" with lower and upper bounds, never "not_blocked".
* Cycles. The guidance is silent on circular ownership. The engine
  computes both the least fixed point (build up from the seeds) and the
  greatest fixed point (assume everything blocked, remove what fails).
  Where they disagree, the status is "indeterminate" and flagged
  cycle-sensitive: the disagreement itself is the finding.
* Bad input. Stakes in one entity summing over 100 percent, duplicate
  edges between the same owner and entity, self-ownership, and
  out-of-range percentages are rejected as input errors. An answer is
  only as traceable as its data.
"""

from dataclasses import dataclass, field

THRESHOLD = 50.0
EPS = 1e-9


class InputError(ValueError):
    """Raised when the ownership input is invalid and no answer is safe."""


@dataclass(frozen=True)
class Seed:
    """A designated person. Only status == 'blocked' seeds the rule.

    Other designations (e.g. Directive-listed entities under the Russia
    program) are recorded and reported but are not treated as blocked
    persons; their prohibitions are set by each Directive and can be
    narrower than full blocking.
    """

    name: str
    program: str = "unspecified"
    status: str = "blocked"


@dataclass(frozen=True)
class Stake:
    """One ownership edge: owner holds pct percent of entity.

    pct=None means the stake exists but its size is unknown (analyst has
    evidence of a holding without a reliable number). source is free-form
    provenance; the engine carries it, never invents it.
    """

    owner: str
    entity: str
    pct: float | None
    source: str = ""


@dataclass
class EntityResult:
    name: str
    is_seed: bool = False
    status: str = "not_blocked"  # blocked | not_blocked | indeterminate
    aggregate_pct: float = 0.0  # known stakes from owners blocked in the least fixed point
    upper_pct: float = 0.0  # aggregate plus unknown stakes maxed at 100%
    contributors: list = field(default_factory=list)  # (owner, pct, source)
    unknown_edges: list = field(default_factory=list)  # (owner, entity) unknowns relied on in the upper bound
    reasons: list = field(default_factory=list)
    cycle_sensitive: bool = False
    naive_pct: float | None = None
    naive_status: str | None = None
    naive_disagrees: bool = False


def validate(stakes: list[Stake]) -> None:
    """Reject inputs where no answer would be traceable."""
    seen: dict[tuple[str, str], Stake] = {}
    for s in stakes:
        if s.owner == s.entity:
            raise InputError(f"self-ownership edge: {s.owner!r} owns itself")
        if s.pct is None:
            continue
        if not (0 < s.pct <= 100):
            raise InputError(f"stake out of range (0, 100]: {s.owner!r} -> {s.entity!r} = {s.pct}")
        key = (s.owner, s.entity)
        if key in seen:
            prev = seen[key]
            raise InputError(
                f"duplicate edge {s.owner!r} -> {s.entity!r} ({prev.pct}% vs {s.pct}%): "
                "without provenance the engine cannot tell a duplicate from a second holding; "
                "de-duplicate the input or attach distinct sources and merge deliberately"
            )
        seen[key] = s
    totals: dict[str, float] = {}
    for s in seen.values():
        totals[s.entity] = totals.get(s.entity, 0.0) + s.pct
    for entity, total in totals.items():
        if total > 100 + EPS:
            raise InputError(
                f"stakes in {entity!r} sum to {total:.4g}% (> 100%): input is invalid, fix the data"
            )


def _fixed_point(nodes, edges, seeds, greatest):
    """Least or greatest fixed point of the blocked-set operator.

    edges: list of (owner, entity, pct) with unknowns already resolved.
    Least: start from seeds, add entities that clear 50% from blocked owners.
    Greatest: start from everything blocked, remove entities that fail.
    """
    blocked = set(nodes) if greatest else set(seeds)
    if greatest:
        blocked |= set(seeds)
    changed = True
    while changed:
        changed = False
        if greatest:
            for e in sorted(blocked - set(seeds)):
                agg = sum(p for (o, ee, p) in edges if ee == e and o in blocked)
                if agg < THRESHOLD - EPS:
                    blocked.discard(e)
                    changed = True
        else:
            for e in sorted(set(nodes) - blocked):
                agg = sum(p for (o, ee, p) in edges if ee == e and o in blocked)
                if agg >= THRESHOLD - EPS:
                    blocked.add(e)
                    changed = True
    return blocked


def _naive_effective(nodes, edges, seeds):
    """Path-product effective ownership, for teaching contrast only.

    Sums, over every simple path from a blocked seed, the product of the
    stakes along the path. This is the usual beneficial-ownership
    calculation and is NOT OFAC's method: the FAQ 401 examples show the
    two disagreeing.
    """
    adj: dict[str, list] = {}
    for (o, e, p) in edges:
        adj.setdefault(o, []).append((e, p))
    totals = {n: 0.0 for n in nodes}

    def walk(node, acc, visited):
        for (nxt, p) in adj.get(node, []):
            if nxt in visited:
                continue
            totals[nxt] += acc * p / 100.0
            walk(nxt, acc * p / 100.0, visited | {nxt})

    for s in seeds:
        walk(s, 100.0, {s})
    return totals


def evaluate(seeds: list[Seed], stakes: list[Stake], compare_naive: bool = False) -> dict:
    """Evaluate every entity under the 50 Percent Rule.

    Returns {entity_name: EntityResult}. Raises InputError on invalid data.
    """
    validate(stakes)
    seed_map = {s.name: s for s in seeds}
    applied = {s.name for s in seeds if s.status == "blocked"}
    nodes = set(seed_map) | {s.owner for s in stakes} | {s.entity for s in stakes}

    def edges_with(unknown_at: float):
        return [(s.owner, s.entity, s.pct if s.pct is not None else unknown_at) for s in stakes]

    edges0 = edges_with(0.0)
    edges100 = edges_with(100.0)

    low = _fixed_point(nodes, edges0, applied, greatest=False)
    high = _fixed_point(nodes, edges100, applied, greatest=True)
    gfp0 = _fixed_point(nodes, edges0, applied, greatest=True)

    naive = _naive_effective(nodes, edges0, applied) if compare_naive else None

    results = {}
    for e in sorted(nodes):
        r = EntityResult(name=e, is_seed=e in seed_map)
        if e in seed_map:
            seed = seed_map[e]
            if e in applied:
                r.status = "blocked"
                r.reasons.append(f"designated blocked person (program: {seed.program}, status: {seed.status})")
            else:
                r.status = "not_blocked"
                r.reasons.append(
                    f"designated with status {seed.status!r} (program: {seed.program}) - "
                    "not treated as a blocked person under the 50 Percent Rule; "
                    "its Directive or program terms apply separately"
                )
            results[e] = r
            continue

        known = [(o, p, s.source) for (o, ee, p), s in zip(edges0, stakes)
                 if ee == e and o in low and s.pct is not None]
        r.aggregate_pct = sum(p for (_, p, _) in known)
        r.contributors = sorted(known)
        unknown_in = [(o, ee) for (o, ee, p), s in zip(edges100, stakes)
                      if ee == e and s.pct is None and o in high]
        r.unknown_edges = sorted(unknown_in)
        r.upper_pct = min(100.0, r.aggregate_pct + sum(
            p for (o, ee, p) in edges100 if ee == e and o in high
            and (o, ee) in set(r.unknown_edges)))

        if e in low:
            r.status = "blocked"
            r.reasons.append(
                f"owned {r.aggregate_pct:.4g}% in the aggregate by blocked persons (>= 50%)"
            )
        elif e not in high:
            r.status = "not_blocked"
            r.reasons.append(
                f"aggregate ownership by blocked persons is {r.aggregate_pct:.4g}% "
                "and cannot reach 50% on the known data"
            )
        else:
            r.status = "indeterminate"
            if e in gfp0 - low:
                r.cycle_sensitive = True
                r.reasons.append(
                    "cycle-sensitive: building up from the blocked persons leaves it unblocked, "
                    "but assuming it blocked holds it up through circular stakes; "
                    "OFAC's guidance is silent on circular ownership"
                )
            unknown_relevant = [ue for ue in r.unknown_edges]
            if e not in gfp0 and unknown_relevant:
                r.reasons.append(
                    f"unknown stakes could push it over 50% (known {r.aggregate_pct:.4g}%, "
                    f"up to {r.upper_pct:.4g}%): " +
                    ", ".join(f"{o} -> {t} (size unknown)" for (o, t) in unknown_relevant)
                )
            if not r.reasons:
                r.reasons.append("answer depends on data or modelling choices the engine cannot settle")

        if naive is not None:
            r.naive_pct = naive[e] * 1.0
            r.naive_status = "blocked" if naive[e] >= THRESHOLD - EPS else "not_blocked"
            if r.status != "indeterminate" and r.naive_status != r.status:
                r.naive_disagrees = True
                r.reasons.append(
                    f"naive path-product gives {r.naive_pct:.4g}% ({r.naive_status}); "
                    "path products are not OFAC's method - see FAQ 401"
                )
        results[e] = r
    return results
