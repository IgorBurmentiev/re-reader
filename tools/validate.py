#!/usr/bin/env python3
"""
validate.py — сверяет импортированный контент с эталоном из data/arcs.md.

Читает data/arcs.md (единственный ручной источник правды) и каждый
content/arc-NN/_manifest.json, затем проверяет:
  • число глав против «ожидается»;
  • сплошную нумерацию number (пропуски / дубли), с поправкой на известные
    сдвиги и нестандартные номера из arcs.md;
  • присутствие нестандартных номеров (2.5, 54B, 123 (A) …);
  • фазы: проставлены и не выходят за объявленное «фаз: N»;
  • иллюстрации: сколько привязано, сколько «сирот»;
  • реестр отложенных побочных content/_pending/_index.json.

Ничего не печатает из текста глав. Код возврата 1, если есть FAIL.

    python tools/validate.py                 # все арки
    python tools/validate.py --arc 7 9       # только указанные
    python tools/validate.py --content build/content
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import compress_ranges, force_utf8_stdout, normalize_label

ROOT = Path(__file__).resolve().parent.parent
OK, WARN, FAIL = "ok", "warn", "fail"


# ─────────────────────────── разбор data/arcs.md ───────────────────────────

def parse_arcs_md(path: Path) -> dict[int, dict]:
    arcs: dict[int, dict] = {}
    cur: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s*Арка\s+(\d+(?:\.\d+)?)\s*$", line)
        if m:
            key = m.group(1)
            cur = {"arc": key, "expected": None, "expected_chapters": None,
                   "phases": None, "nonstandard": [], "structure": "", "note": ""}
            arcs[key] = cur
            continue
        if cur is None:
            continue
        if line.startswith("ожидается:"):
            v = line.split(":", 1)[1].strip()
            mm = re.match(r"(\d+)", v)          # заголовочное число («всего блоков»)
            cur["expected"] = int(mm.group(1)) if mm else None
            # уточнение «— N глав + пролог + интерлюдии + …» → это число именно глав
            gm = re.findall(r"(\d+)\s*глав", v)
            tail = v.lower()
            if len(gm) == 1 and any(w in tail for w in
                                    ("пролог", "интерл", "эпилог", "финал",
                                     "послесл", "побочн", "интермед")):
                cur["expected_chapters"] = int(gm[0])
        elif line.startswith("фаз:"):
            mm = re.match(r"\D*(\d+)", line)
            cur["phases"] = int(mm.group(1)) if mm else None
            if re.search(r"процесс|онгоинг|ongoing|ещё|еще", line, re.I):
                cur["phases"] = (cur["phases"] or 0) + 1   # «N полностью, третья в процессе»
                cur["ongoing"] = True
        elif line.startswith("структура:"):
            cur["structure"] = line.split(":", 1)[1].strip()
        elif line.startswith("нестандартные номера:"):
            v = line.split(":", 1)[1]
            for tok in re.findall(r"\d+(?:\.\d+)?\s*(?:\([AБВB]\))?|\d+[AБВB]", v):
                cur["nonstandard"].append(normalize_label(tok))
        elif line.startswith(("примечание:", "дополнительно:")):
            cur["note"] += " " + line.split(":", 1)[1].strip()
    return arcs


# ─────────────────────────── проверки ───────────────────────────

def check_arc(arc_key: str, spec: dict, manifest: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    chapters = manifest.get("chapters", [])
    ch = [c for c in chapters if c.get("type") == "chapter"]

    # 1. число глав
    exp = spec.get("expected_chapters") or spec.get("expected")
    side = len([c for c in chapters if c.get("type") in ("side", "if")])
    if exp is None:
        out.append((WARN, f"эталон числа глав не задан в arcs.md — фактически {len(ch)}"))
    elif len(ch) == exp:
        out.append((OK, f"глав: {len(ch)} = ожидается {exp}"))
    else:
        sev = WARN if abs(len(ch) - exp) <= 2 else FAIL
        extra = f" (+{side} побочных вынесено в _pending)" if side else ""
        out.append((sev, f"глав: {len(ch)}, ожидается {exp} "
                         f"(разница {len(ch) - exp:+d}){extra}"))

    # 2. сплошная нумерация
    nums = []
    for c in ch:
        n = c.get("number")
        if n and str(n).isdigit():
            nums.append(int(n))
    if nums:
        lo, hi = min(nums), max(nums)
        gaps = sorted(set(range(lo, hi + 1)) - set(nums))
        dups = sorted({n for n in nums if nums.count(n) > 1})
        if lo != 1:
            out.append((WARN, f"нумерация number начинается с {lo}, не с 1"))
        if gaps:
            out.append((FAIL, f"пропуски в number: {compress_ranges(gaps)}"))
        if dups:
            out.append((FAIL, f"дубли number: {dups}"))
        if not gaps and not dups and lo == 1:
            out.append((OK, f"number сплошной 1..{hi}"))

    # 3. нестандартные номера
    labels = {normalize_label(str(c.get("label") or c.get("number") or "")) for c in ch}
    for want in spec.get("nonstandard", []):
        if want in labels:
            out.append((OK, f"нестандартный номер присутствует: {want}"))
        else:
            out.append((WARN, f"нестандартный номер из arcs.md не найден: {want}"))

    # 4. фазы
    ph_declared = spec.get("phases")
    ph_seen = sorted({c["phase"] for c in chapters if c.get("phase")})
    if ph_declared:
        if not ph_seen:
            out.append((WARN, f"фаз объявлено {ph_declared}, но во frontmatter phase "
                              f"нигде не проставлен (ставится флагом --phase / вручную)"))
        else:
            bad = [p for p in ph_seen if p > ph_declared]
            if bad:
                out.append((FAIL, f"phase выходит за объявленные {ph_declared}: {bad}"))
            else:
                out.append((OK, f"phase: {ph_seen} ⊆ 1..{ph_declared}"))

    # 5. иллюстрации
    bound = sum(len(c.get("illustrations", [])) for c in chapters)
    total = manifest.get("images_total")
    orphans = manifest.get("orphan_images", [])
    if total is not None and (total > 2 or bound):
        frac = bound / total if total else 1
        sev = OK if (frac >= 0.75 or bound >= total) else WARN
        out.append((sev, f"иллюстрации: привязано {bound}/{total}, сирот {len(orphans)}"))
    elif bound:
        out.append((OK, f"иллюстрации: привязано {bound}, сирот {len(orphans)}"))

    # 6. типы-синонимы: финал/эпилог, пролог-мостик
    kinds = {}
    for c in chapters:
        kinds[c["type"]] = kinds.get(c["type"], 0) + 1
    out.append((OK, "состав: " + ", ".join(f"{k}×{v}" for k, v in sorted(kinds.items()))))
    return out


def check_pending(pending_dir: Path) -> list[tuple[str, str]]:
    idx = pending_dir / "_index.json"
    if not idx.exists():
        return []
    reg = json.loads(idx.read_text("utf-8"))
    out = [(OK, f"_pending: {len(reg)} историй в реестре")]
    for e in reg:
        miss = [k for k in ("title", "type", "parts", "status") if not e.get(k)]
        if miss:
            out.append((WARN, f"  {e.get('slug', '?')}: не заполнено {miss}"))
        if e.get("read_after") is None:
            out.append((WARN, f"  {e.get('slug', '?')}: read_after не определён"))
        files = list(pending_dir.glob(f"side/{e['slug']}*.md"))
        if len(files) != e.get("parts"):
            out.append((WARN, f"  {e['slug']}: файлов {len(files)}, в реестре parts={e.get('parts')}"))
    return out


# ─────────────────────────── main ───────────────────────────

def main() -> None:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", type=Path, default=ROOT / "content")
    ap.add_argument("--arcs-md", type=Path, default=ROOT / "data" / "arcs.md")
    ap.add_argument("--arc", nargs="*", default=None,
                    help="проверить только эти арки (напр. --arc 7 9 4.5)")
    args = ap.parse_args()

    spec = parse_arcs_md(args.arcs_md)
    worst = OK
    rank = {OK: 0, WARN: 1, FAIL: 2}

    manifests = sorted(args.content.glob("arc-*/_manifest.json"))
    if not manifests:
        print(f"нет ни одного {args.content}/arc-*/_manifest.json — сначала импорт")
        sys.exit(1)

    for mf in manifests:
        m = re.match(r"arc-0*(\d+)(?:-(\d+))?$", mf.parent.name)
        if not m:
            continue
        arc_key = m.group(1) + (f".{m.group(2)}" if m.group(2) else "")
        if args.arc and arc_key not in args.arc:
            continue
        manifest = json.loads(mf.read_text("utf-8"))
        arc_spec = spec.get(arc_key, {})
        print(f"\n━━━ Арка {arc_key}  ({mf.parent.name}) ━━━")
        for sev, msg in check_arc(arc_key, arc_spec, manifest):
            print(f"  [{sev.upper():4}] {msg}")
            worst = sev if rank[sev] > rank[worst] else worst

    pend = check_pending(args.content / "_pending")
    if pend:
        print("\n━━━ Отложенные побочные ━━━")
        for sev, msg in pend:
            print(f"  [{sev.upper():4}] {msg}")
            worst = sev if rank[sev] > rank[worst] else worst

    print(f"\nИТОГ: {worst.upper()}")
    sys.exit(1 if worst == FAIL else 0)


if __name__ == "__main__":
    main()
