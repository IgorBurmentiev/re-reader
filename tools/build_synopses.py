#!/usr/bin/env python3
"""
build_synopses.py — synopses/syn_Narc.txt → content/arc-NN/_synopsis.md

Синопсисы из файлов автора (ТЗ §8) кладём рядом с главами. Первая строка файла —
часто название в кавычках, её отбрасываем (оно уже в arcs.md). Идемпотентно.

    python tools/build_synopses.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import arc_folder, force_utf8_stdout, normalize_typography

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    force_utf8_stdout()
    src = ROOT / "synopses"
    content = ROOT / "content"
    done = 0
    for f in sorted(src.glob("syn_*arc.txt")):
        m = re.search(r"syn_(\d+)arc", f.name)
        if not m:
            continue
        arc = m.group(1)
        out = content / arc_folder(arc)
        if not out.exists():
            print(f"арка {arc}: нет {out} — пропуск")
            continue
        raw = f.read_text(encoding="utf-8", errors="replace").strip()
        # первая строка — название в кавычках, убираем
        lines = raw.split("\n")
        if lines and re.match(r'^\s*[«"“].*[»"”]\s*$', lines[0]):
            lines = lines[1:]
        body = normalize_typography("\n\n".join(
            p.strip() for p in re.split(r"\n\s*\n", "\n".join(lines)) if p.strip()))
        (out / "_synopsis.md").write_text(body + "\n", encoding="utf-8", newline="\n")
        done += 1
        print(f"арка {arc}: _synopsis.md ({len(body)} символов)")
    print(f"\nвсего: {done}")


if __name__ == "__main__":
    main()
