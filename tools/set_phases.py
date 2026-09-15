#!/usr/bin/env python3
"""
set_phases.py — проставляет frontmatter-поле phase по разбивке из data/arcs.md.

ТЗ: соответствие «глава → фаза» для части арок известно из файлов, для части —
со слов и требует проверки после импорта. Этот шаг применяет диапазоны из
arcs.md к уже импортированным главам. Идемпотентен, запускать после import_all.

  python tools/set_phases.py                 # все арки, у которых в arcs.md есть фазы
  python tools/set_phases.py --arc 4 5 6
  python tools/set_phases.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import arc_folder, force_utf8_stdout

ROOT = Path(__file__).resolve().parent.parent


def parse_phase_ranges(arcs_md: Path) -> dict[str, dict[int, list[tuple[int, int]]]]:
    """{ '4': {1: [(1,23)], 2: [(24,51)], ...}, ... }"""
    out: dict[str, dict[int, list[tuple[int, int]]]] = {}
    cur_arc: str | None = None
    cur_phase: int | None = None
    lines = arcs_md.read_text(encoding="utf-8").splitlines()
    for line in lines:
        m = re.match(r"^##\s*Арка\s+(\d+(?:\.\d+)?)", line)
        if m:
            cur_arc, cur_phase = m.group(1), None
            continue
        if cur_arc is None:
            continue
        mp = re.match(r"^\s*фаза\s*(\d+)\s*:(.*)$", line)
        if mp:
            cur_phase = int(mp.group(1))
            out.setdefault(cur_arc, {}).setdefault(cur_phase, [])
            rest = mp.group(2)
        elif cur_phase is not None and line.startswith("    "):
            rest = line                      # продолжение блока фазы
        else:
            if not re.match(r"^\s{2,}", line):
                cur_phase = None
            continue
        for a, b in re.findall(r"(\d+)\s*[–—-]\s*(\d+)", rest):
            out[cur_arc][cur_phase].append((int(a), int(b)))
        for solo in re.findall(r"глав[аы]?\s+(\d+)(?!\s*[–—-]\s*\d)", rest):
            out[cur_arc][cur_phase].append((int(solo), int(solo)))
    return {k: v for k, v in out.items() if any(v.values())}


def phase_of(n: int, ranges: dict[int, list[tuple[int, int]]]) -> int | None:
    for ph, spans in ranges.items():
        for a, b in spans:
            if a <= n <= b:
                return ph
    return None


def set_fm_phase(md: Path, phase: int) -> bool:
    text = md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return False
    fm, body = m.group(1), m.group(2)
    if re.search(r"^phase:\s*" + str(phase) + r"\s*$", fm, re.M):
        return False
    fm = re.sub(r"^phase:.*\n?", "", fm, flags=re.M).rstrip()
    # phase ставим сразу после arc (или volume), чтобы совпасть с порядком _common
    if re.search(r"^volume:", fm, re.M):
        fm = re.sub(r"(^volume:.*$)", r"\1\nphase: " + str(phase), fm, count=1, flags=re.M)
    elif re.search(r"^arc:", fm, re.M):
        fm = re.sub(r"(^arc:.*$)", r"\1\nphase: " + str(phase), fm, count=1, flags=re.M)
    else:
        fm = f"phase: {phase}\n" + fm
    md.write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8")
    return True


def main() -> None:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", type=Path, default=ROOT / "content")
    ap.add_argument("--arcs-md", type=Path, default=ROOT / "data" / "arcs.md")
    ap.add_argument("--arc", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ranges_by_arc = parse_phase_ranges(args.arcs_md)
    total_changed = 0
    for arc_key, ranges in sorted(ranges_by_arc.items()):
        if args.arc and arc_key not in args.arc:
            continue
        folder = args.content / arc_folder(arc_key)
        mf = folder / "_manifest.json"
        if not mf.exists():
            print(f"арка {arc_key}: нет {mf} — пропуск")
            continue
        rows = json.loads(mf.read_text("utf-8")).get("chapters", [])
        # фаза для главы — по номеру. Для не-глав:
        #   • пролог открывает новый раздел  → фаза СЛЕДУЮЩЕЙ главы;
        #   • интерлюдия / эпилог / бонус закрывают раздел → фаза ПРЕДЫДУЩЕЙ главы
        #     (если предыдущей нет — берём следующую).
        # Раньше всё тянулось от следующей главы, из-за чего послесловия и
        # финальные интерлюдии («Золото и золото», «Убирк») уезжали в чужую фазу.
        OPENS_SECTION = {"prologue"}
        phase_by_slug: dict[str, int] = {}
        last_ch_phase = None
        pending_specials: list[tuple[str, str]] = []  # (slug, type)
        for r in rows:
            if r["type"] == "chapter" and str(r.get("number") or "").isdigit():
                ph = phase_of(int(r["number"]), ranges)
                if ph:
                    for s, t in pending_specials:
                        phase_by_slug[s] = (
                            ph if t in OPENS_SECTION or last_ch_phase is None
                            else last_ch_phase
                        )
                    pending_specials.clear()
                    phase_by_slug[r["slug"]] = ph
                    last_ch_phase = ph
            else:
                pending_specials.append((r["slug"], r["type"]))
        for s, _t in pending_specials:        # хвостовые не-главы — фаза последней главы
            if last_ch_phase:
                phase_by_slug[s] = last_ch_phase

        changed = 0
        for r in rows:
            ph = phase_by_slug.get(r["slug"])
            if not ph:
                continue
            md = folder / f"{r['slug']}.md"
            if not md.exists():
                continue
            if args.dry_run:
                if r.get("phase") != ph:
                    changed += 1
                continue
            wrote = set_fm_phase(md, ph)
            if r.get("phase") != ph:
                r["phase"] = ph
                changed += 1
            elif wrote:
                changed += 1
        if not args.dry_run and changed:
            data = json.loads(mf.read_text("utf-8"))
            data["chapters"] = rows
            mf.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        seen_ph = sorted(set(phase_by_slug.values()))
        print(f"арка {arc_key}: фазы {seen_ph}, "
              f"{'проставит' if args.dry_run else 'проставлено'} {changed} файлов "
              f"из {len(rows)}")
        total_changed += changed
    print(f"\nвсего изменений: {total_changed}"
          + ("  (--dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
