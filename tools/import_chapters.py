#!/usr/bin/env python3
"""
import_chapters.py — режет монолитный файл (txt / md / docx / html) на главы.
Запасной конвертер: когда источник не FB2/EPUB/PDF, а один сплошной файл.

Спойлер-безопасно: в консоль только номера и статистика. Названия глав —
с флагом --show-titles.

Примеры:
    # посмотреть, как разрежется, ничего не записывая
    python import_chapters.py arc.txt --arc 7 --dry-run

    # свой разделитель глав (первая группа — номер, вторая — название)
    python import_chapters.py arc.txt --arc 7 --dry-run \
        --pattern '^\\s*Глава\\s+(\\d+[AБВB]?)[.\\s—:-]*(.*)$'

    # записать результат
    python import_chapters.py arc.txt --arc 7 --out content/arc-07
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    Chapter, Reporter, SCENE_BREAK, assign_numbers, classify_heading,
    force_utf8_stdout, is_scene_break, manifest_rows,
    normalize_typography, trim_scene_breaks, write_chapter, write_manifest_rows,
)


# ─────────────────────────── чтение источника ───────────────────────────

def read_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        try:
            import docx
        except ImportError:
            sys.exit("Для .docx нужен python-docx:  pip install python-docx")
        return "\n\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    if suffix in {".html", ".htm"}:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            sys.exit("Для .html нужен beautifulsoup4:  pip install beautifulsoup4")
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"),
                             "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return "\n\n".join(el.get_text(" ", strip=True)
                           for el in soup.find_all(["p", "h1", "h2", "h3", "h4"]))
    sys.exit(f"Неизвестный формат: {suffix}")


# ─────────────────────────── разбиение ───────────────────────────

def split_chapters(text: str, *, user_patterns: list[str], default_phase):
    lines = text.split("\n")
    pats = [re.compile(p) for p in user_patterns] if user_patterns else None

    heads: list[tuple[int, dict, int | None]] = []   # (line_idx, info, phase)
    phase = default_phase
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) > 120:
            continue
        info = None
        if pats:
            for pat in pats:
                m = pat.match(s)
                if m:
                    num = (m.group(1) or "").strip() if m.lastindex else ""
                    ttl = (m.group(2) or "").strip() if m.lastindex and m.lastindex >= 2 else ""
                    info = {"kind": "chapter", "label": num, "title": ttl}
                    break
        if info is None:
            info = classify_heading(s)
        if not info:
            continue
        if info["kind"] == "phase":
            phase = int(info["label"])
            continue
        heads.append((i, info, phase))

    if not heads:
        sys.exit("Заголовки не найдены. Задай свой --pattern и прогони с --dry-run.")

    chapters: list[Chapter] = []
    for idx, (ln, info, ph) in enumerate(heads):
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        raw = "\n".join(lines[ln + 1:end])
        parts = []
        for para in re.split(r"\n\s*\n", raw):
            para = para.strip()
            if not para:
                continue
            parts.append(SCENE_BREAK if is_scene_break(para) else para)
        chapters.append(Chapter(
            kind=info["kind"], label=info["label"], title=info["title"],
            body="\n\n".join(parts), phase=ph, source_ref=f"line {ln + 1}",
        ))
    return chapters


# ─────────────────────────── main ───────────────────────────

def main() -> None:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("--arc", type=int, required=True)
    ap.add_argument("--out", type=Path, default=None, help="куда писать (без него — dry-run)")
    ap.add_argument("--volume", type=int, default=None)
    ap.add_argument("--phase", type=int, default=None)
    ap.add_argument("--offset", type=int, default=0, help="сдвиг сквозной нумерации глав")
    ap.add_argument("--pattern", action="append", default=[],
                    help="свой regex заголовка: (1)=номер, (2)=название")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show-titles", action="store_true")
    args = ap.parse_args()

    text = read_source(args.source)
    chapters = split_chapters(text, user_patterns=args.pattern,
                              default_phase=args.phase)
    for ch in chapters:
        ch.volume = args.volume
        ch.body = trim_scene_breaks(normalize_typography(ch.body))

    report = assign_numbers(chapters, offset=args.offset)
    rep = Reporter(args.show_titles)
    rep.table(chapters)
    rep.summary(chapters, report)

    if args.dry_run or not args.out:
        print("\n(dry-run — ничего не записано; добавь --out)")
        return

    seen: dict[str, int] = {}
    for ch in chapters:
        idx = seen.get(ch.kind, 0)
        seen[ch.kind] = idx + 1
        write_chapter(args.out, ch, args.arc, index=idx)
    write_manifest_rows(args.out, manifest_rows(chapters), extra={
        "arc": args.arc, "volume": args.volume, "source": args.source.name,
        "generator": "import_chapters.py",
    })
    print(f"\nзаписано в {args.out}: {len(chapters)} файлов")


if __name__ == "__main__":
    main()
