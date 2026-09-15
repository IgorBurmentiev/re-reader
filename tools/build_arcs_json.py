#!/usr/bin/env python3
"""
build_arcs_json.py — data/arcs.md (ручной) → data/arcs.json (для сборки сайта).

arcs.md остаётся источником правды; json — его машинная проекция, которую
читает Astro. Перегенерировать после правок arcs.md.

    python tools/build_arcs_json.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import arc_folder, force_utf8_stdout, normalize_label
from set_phases import parse_phase_ranges

ROOT = Path(__file__).resolve().parent.parent

# парные светлые темы из ТЗ §6
THEME_PAIR = {
    "amethyst": "lavender", "midnight": "parchment", "lagoon": "lagoon-light",
    "conifer": "mint", "ash": "mist", "wormwood": "meadow", "frost": "crust",
    "sakura": "blush", "ember": "dawn", "nocturne": "sepia",
}


def parse(md: Path) -> list[dict]:
    arcs: list[dict] = []
    cur: dict | None = None
    for line in md.read_text(encoding="utf-8").splitlines():
        h = re.match(r"^##\s*Арка\s+(\d+(?:\.\d+)?)\s*$", line)
        if h:
            cur = {"arc": h.group(1), "slug": arc_folder(h.group(1))}
            arcs.append(cur)
            continue
        if cur is None or ":" not in line or line.startswith(" "):
            continue
        key, val = (x.strip() for x in line.split(":", 1))
        if key == "название":
            cur["title"] = val
        elif key == "также известна как":
            cur["aka"] = [x.strip() for x in re.split(r"[/·]", val) if x.strip()]
        elif key == "тема":
            cur["theme"] = val
            cur["theme_light"] = THEME_PAIR.get(val, val)
        elif key == "тома":
            cur["volumes"] = val
        elif key == "структура":
            cur["structure"] = val.split()[0]
        elif key == "статус":
            cur["status"] = val
        elif key == "ожидается":
            m = re.match(r"(\d+)", val)
            cur["expected_total"] = int(m.group(1)) if m else None
            gm = re.findall(r"(\d+)\s*глав", val)
            if len(gm) == 1 and re.search(r"пролог|интерл|эпилог|финал|побочн", val.lower()):
                cur["expected_chapters"] = int(gm[0])
        elif key == "нестандартные номера":
            cur["nonstandard"] = [normalize_label(t) for t in
                                  re.findall(r"\d+(?:\.\d+)?\s*\([A-ZА-Я]\)|\d+[A-ZА-Я]|\d+\.\d+", val)]
    return arcs


def main() -> None:
    force_utf8_stdout()
    md = ROOT / "data" / "arcs.md"
    arcs = parse(md)
    phase_ranges = parse_phase_ranges(md)
    for a in arcs:
        pr = phase_ranges.get(a["arc"])
        if pr:
            a["phases"] = [{"n": n, "ranges": [[x, y] for x, y in sorted(sp)]}
                           for n, sp in sorted(pr.items())]
    out = ROOT / "data" / "arcs.json"
    out.write_text(json.dumps(arcs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"записано {out}: {len(arcs)} арок")
    for a in arcs:
        print(f"  {a['slug']:10} {a.get('title', '?'):32} тема={a.get('theme', '?'):10} "
              f"фаз={len(a.get('phases', []))}")


if __name__ == "__main__":
    main()
