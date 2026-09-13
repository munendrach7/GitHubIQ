"""Adaptive output scale — makes the guide grow with the repository.

A tiny repo and a huge monorepo should NOT produce a similar-sized guide. Here we
derive the target counts every generative agent aims for (how many components,
architecture nodes, data-flow steps, tutor lessons and per-component deep dives)
from two signals:

* **repo size** — the number of files captured, bucketed small → very large;
* **the learner's depth preference** — quick / guided / deep scales the ranges.

Agents pass these ranges into their prompts, so a large repo yields a broad,
comprehensive guide that covers every part, while a small one stays focused.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputScale:
    size_label: str
    components: tuple[int, int]   # how many software components to identify
    nodes: tuple[int, int]        # architecture nodes
    steps: tuple[int, int]        # data-flow steps
    lessons: tuple[int, int]      # tutor language/idiom lessons
    max_deepdives: int            # cap on per-component deep-dive sections
    deep_budget: int              # char budget for a component's source context


# bucket -> (components, nodes, steps, lessons)
_BASE = {
    0: ((3, 6), (5, 8), (5, 7), (3, 4)),
    1: ((6, 12), (8, 14), (6, 9), (4, 6)),
    2: ((10, 18), (12, 20), (8, 12), (5, 8)),
    3: ((16, 30), (16, 28), (9, 14), (6, 10)),
}
_LABELS = {0: "small", 1: "medium", 2: "large", 3: "very large"}
_DEEP_BUDGET = {0: 60_000, 1: 90_000, 2: 120_000, 3: 150_000}
_DEPTH_FACTOR = {"quick": 0.7, "guided": 1.0, "deep": 1.4}

# Hard ceilings so a pathological repo can't explode cost/latency.
_STEP_CAP = 16
_LESSON_CAP = 12
_NODE_CAP = 32
_COMPONENT_CAP = 36


def _bucket(file_count: int) -> int:
    if file_count < 80:
        return 0
    if file_count < 300:
        return 1
    if file_count < 800:
        return 2
    return 3


def compute_scale(file_count: int, depth) -> OutputScale:
    """Derive target ranges from repo size and the depth preference."""
    b = _bucket(file_count or 0)
    comp, nodes, steps, lessons = _BASE[b]
    depth_val = getattr(depth, "value", depth) or "guided"
    f = _DEPTH_FACTOR.get(depth_val, 1.0)

    def scaled(rng: tuple[int, int], cap: int, floor_lo: int = 1) -> tuple[int, int]:
        lo, hi = rng
        return (
            max(floor_lo, min(cap, round(lo * f))),
            max(floor_lo + 1, min(cap, round(hi * f))),
        )

    comp_r = scaled(comp, _COMPONENT_CAP, floor_lo=2)
    node_r = scaled(nodes, _NODE_CAP, floor_lo=3)
    step_r = scaled(steps, _STEP_CAP, floor_lo=4)
    lesson_r = scaled(lessons, _LESSON_CAP, floor_lo=3)
    return OutputScale(
        size_label=_LABELS[b],
        components=comp_r,
        nodes=node_r,
        steps=step_r,
        lessons=lesson_r,
        max_deepdives=comp_r[1],
        deep_budget=_DEEP_BUDGET[b],
    )
