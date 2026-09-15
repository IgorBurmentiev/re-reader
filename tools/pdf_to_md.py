#!/usr/bin/env python3
"""
pdf_to_md.py — конвертер PDF (с текстовым слоем и без) в структуру читалки.

Две ветки, ТЗ §4:
  • текстовый слой (арки 4, 6) — вытаскиваем через PyMuPDF. Заголовок ищем
    по связке «жирный + крупнее основного кегля», регуляркой добираем случаи,
    где стиль не отличается. Название в PDF нередко переносится на 2 строки —
    склеиваем. Иллюстрации-страницы (целиком картинка) вынимаем в images/.
  • OCR-хвост (арка 4.5, стр. ~1738–1830 в PDF арки 4 — «сняты картинками»):
    флаг --ocr-pages A-B. Страница растрируется в 300 dpi и распознаётся
    tesseract --l rus. Считается средняя уверенность, слова ниже порога
    выписываются в _ocr_review.md для разовой правки (не вычиткой всего текста).

В консоль — только цифры. Названия глав — с флагом --show-titles.

Требуется: pip install pymupdf ;  tesseract + языковой пакет rus (в PATH или --tesseract).

Примеры:
  # арка 6 — только текстовый слой
  python pdf_to_md.py "Арка 6 Re_Zero.pdf" --arc 6 --out content/arc-06

  # арка 4 — текстовый слой до эпилога включительно
  python pdf_to_md.py "Арка 4 + 4.5 ReZero.pdf" --arc 4 --text-pages 1-1737 \
      --out content/arc-04

  # арка 4.5 — OCR-хвост в отдельную папку, своя нумерация с первой главы
  python pdf_to_md.py "Арка 4 + 4.5 ReZero.pdf" --arc 4 --volume 0 \
      --ocr-pages 1738-1830 --ocr-only --out content/arc-04.5
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import pymupdf
except ImportError:
    sys.exit("Нужен PyMuPDF:  pip install pymupdf")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    Chapter, Reporter, SCENE_BREAK, assign_numbers, classify_heading,
    compress_ranges, force_utf8_stdout, manifest_rows,
    normalize_typography, trim_scene_breaks, write_chapter, write_manifest_rows,
)
from _common import _trim_title  # noqa: E402


# ─────────────────────────── диапазоны страниц ───────────────────────────

def parse_ranges(spec: str, npages: int) -> list[int]:
    """'1-5,8,10-12' → отсортированный список 0-based индексов."""
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a.strip() else 1
            b = int(b) if b.strip() else npages
            out.update(range(a - 1, b))
        else:
            out.add(int(part) - 1)
    return sorted(i for i in out if 0 <= i < npages)


# ─────────────────────────── текстовый слой ───────────────────────────

def _page_lines(page) -> list[dict]:
    """Строки страницы (сверху вниз) со сведениями о кегле/жирности.

    PyMuPDF иногда отдаёт блоки не в порядке чтения (в арке 6 шапка главы
    оказывается последним блоком) — поэтому сортируем по вертикали.
    """
    d = page.get_text("dict")
    lines = []
    for block in d["blocks"]:
        for ln in block.get("lines", []):
            spans = ln["spans"]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans)
            if not text.strip():
                continue
            big = max(spans, key=lambda s: len(s["text"]))
            bold = any(("bold" in s["font"].lower() or s["flags"] & 2 ** 4)
                       for s in spans)
            lines.append({
                "text": text, "size": round(big["size"], 1), "bold": bold,
                "y": round(ln["bbox"][1], 1), "x": round(ln["bbox"][0], 1),
            })
    lines.sort(key=lambda l: (l["y"], l["x"]))
    return lines


def _body_size(all_lines: list[dict]) -> float:
    """Модальный кегль — это основной текст."""
    from collections import Counter
    c = Counter(l["size"] for l in all_lines if len(l["text"]) > 40)
    return c.most_common(1)[0][0] if c else 11.0


def extract_text_chapters(doc, pages: list[int], *, arc: int,
                          heading_gap: float) -> tuple[list[Chapter], list[int]]:
    all_lines: list[tuple[int, dict]] = []
    for p in pages:
        for ln in _page_lines(doc[p]):
            all_lines.append((p, ln))
    body_size = _body_size([l for _, l in all_lines])
    big = body_size + heading_gap

    chapters: list[Chapter] = []
    cur: Chapter | None = None
    buf: list[str] = []
    in_title = False                     # идёт ли ещё перенесённое название
    image_pages: list[int] = []
    seen_pages_with_text = set(p for p, _ in all_lines)
    for p in pages:
        if p not in seen_pages_with_text:
            image_pages.append(p)

    # запасная регулярка на случай, если у заголовка не проставлен bold
    strict_head = re.compile(r"^\s*(?:арка\s*\d+\s*[—–\-]\s*)?"
                             r"(глава|пролог|эпилог|интерлюдия|интермедия)\b"
                             r".{0,85}$", re.I)
    credit = re.compile(r"^\s*(перевод|переводчик|редактура|редактор|источник|"
                        r"тайпсет|оформл|https?://|vk\.com|t\.me|@)", re.I)

    def flush():
        nonlocal buf
        if cur is not None:
            cur.body = "\n\n".join(x for x in buf if x.strip())
        buf = []

    last_head_line = -10
    for i, (p, ln) in enumerate(all_lines):
        t = re.sub(r"\s{2,}", " ", ln["text"].strip())
        looks_big = ln["bold"] and ln["size"] >= big - 0.3
        gate = looks_big or (strict_head.match(t) is not None)
        info = classify_heading(t) if gate else None

        # перенесённое название: «Глава 20. Шаула ≠ Мудрец =» + «Флюгель»
        if in_title and cur is not None:
            if looks_big and not info and len(t) < 70:
                cur.title = (cur.title + " " + t).strip(" .")
                last_head_line = i
                continue
            in_title = False

        if info and info["kind"] != "phase" and i - last_head_line > 1:
            flush()
            cur = Chapter(kind=info["kind"], label=info["label"],
                          title=info["title"], source_ref=f"pdf p.{p + 1}")
            chapters.append(cur)
            last_head_line = i
            in_title = True             # вдруг название продолжится на след. строке
            continue

        if cur is None:
            continue
        # шапка перевода сразу после заголовка → в поля, не в тело
        if i - last_head_line <= 4 and credit.match(t):
            low = t.lower()
            if low.startswith(("перевод", "тайпсет", "оформл", "редакту", "редакто")):
                cur.translator = (cur.translator + "; " + t).strip("; ")
            if re.search(r"https?://|vk\.com|t\.me", t):
                m = re.search(r"(https?://\S+|vk\.com/\S+|t\.me/\S+)", t)
                if m and not cur.source:
                    cur.source = m.group(1)
            continue
        buf.append(SCENE_BREAK if _is_scene_line(t) else t)
    flush()

    # склейка строк одного абзаца (PDF рвёт абзац на строки) + финальная чистка названий
    for ch in chapters:
        ch.body = _reflow(ch.body)
        ch.title = _trim_title(ch.title)
    return chapters, image_pages


_SCENE_CHARS = "*※＊✽✼❋◆◇■□▲△▼▽●○·•"


def _is_scene_line(t: str) -> bool:
    s = re.sub(r"\s+", "", t)
    return bool(s) and len(s) <= 20 and all(c in _SCENE_CHARS for c in s)


def _reflow(body: str) -> str:
    """PDF-строки → абзацы. Новый абзац: пустая строка, либо строка,
    начинающаяся с — реплики / заглавной после точки на предыдущей."""
    out: list[str] = []
    cur = ""
    for raw in body.split("\n\n"):
        line = raw.strip()
        if not line:
            continue
        if line == SCENE_BREAK:
            if cur:
                out.append(cur); cur = ""
            out.append(SCENE_BREAK)
            continue
        if not cur:
            cur = line
        elif re.match(r"^[—\-«]", line) or (cur[-1:] in ".!?…»" and line[:1].isupper()):
            out.append(cur); cur = line
        elif cur.endswith("-"):
            cur = cur[:-1] + line
        else:
            cur += " " + line
    if cur:
        out.append(cur)
    return "\n\n".join(out)


# ─────────────────────────── иллюстрации ───────────────────────────

def dump_page_images(doc, page_idx: int, out_dir: Path, tag: str) -> list[str]:
    names = []
    page = doc[page_idx]
    for n, img in enumerate(page.get_images(full=True), 1):
        xref = img[0]
        try:
            ext = doc.extract_image(xref)
        except Exception:
            continue
        data, e = ext["image"], ext["ext"]
        if len(data) < 8000:            # мелочь (иконки, линейки) — мимо
            continue
        name = f"{tag}.{e}" if n == 1 else f"{tag}-{n}.{e}"
        (out_dir / name).write_bytes(data)
        names.append(name)
    return names


# ─────────────────────────── OCR-ветка ───────────────────────────

def find_tesseract(explicit: str | None) -> str:
    if explicit:
        return explicit
    for c in ("tesseract",
              r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if shutil.which(c) or Path(c).exists():
            return c
    sys.exit("tesseract не найден. Укажи путь через --tesseract или добавь в PATH.")


def ocr_page(doc, page_idx: int, tess: str, dpi: int, lang: str,
             workdir: Path) -> tuple[str, list[tuple[str, float]], float]:
    """→ (text с разбивкой на абзацы, [(word, conf)], mean_conf).

    Абзацы восстанавливаем по геометрии (вертикальный зазор между строками и
    отступ первой строки), а не по разметке tesseract — она на фото-страницах
    ненадёжна.
    """
    pix = doc[page_idx].get_pixmap(dpi=dpi)
    png = workdir / f"p{page_idx + 1}.png"
    pix.save(png)
    base = workdir / f"p{page_idx + 1}"
    subprocess.run([tess, str(png), str(base), "-l", lang, "--psm", "3", "tsv"],
                   check=True, capture_output=True)
    tsv = base.with_suffix(".tsv").read_text(encoding="utf-8", errors="replace")

    words: list[tuple[str, float]] = []
    lines: dict[tuple, dict] = {}
    for row in tsv.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        conf = float(f[10])
        left, top, h = int(f[6]), int(f[7]), int(f[9])
        words.append((f[11], conf))
        key = (int(f[2]), int(f[3]), int(f[4]))            # block/par/line
        ln = lines.setdefault(key, {"top": top, "left": left, "h": h,
                                    "words": [], "wn": []})
        ln["wn"].append((int(f[5]), f[11]))
        ln["left"] = min(ln["left"], left)
        ln["top"] = min(ln["top"], top)
        ln["h"] = max(ln["h"], h)
    for ln in lines.values():
        ln["words"] = [w for _, w in sorted(ln["wn"])]

    ordered = sorted(lines.values(), key=lambda l: (l["top"], l["left"]))
    hs = sorted(l["h"] for l in ordered) or [1]
    med_h = hs[len(hs) // 2] or 1
    left_min = min((l["left"] for l in ordered), default=0)
    # типичный шаг строки — медиана вертикальных зазоров
    gaps = sorted(ordered[i]["top"] - ordered[i - 1]["top"]
                  for i in range(1, len(ordered)))
    step = gaps[len(gaps) // 2] if gaps else med_h
    paras: list[str] = []
    prev_top = None
    for l in ordered:
        text = " ".join(l["words"])
        new_para = (
            prev_top is None
            or l["top"] - prev_top > step * 1.6               # пропущенная строка
            or l["left"] - left_min > med_h * 0.8             # красная строка
        )
        if new_para or not paras:
            paras.append(text)
        else:
            paras[-1] += " " + text
        prev_top = l["top"]

    confs = [c for _, c in words if c >= 0]
    mean = sum(confs) / len(confs) if confs else 0.0
    return "\n\n".join(paras), words, mean


def run_ocr(doc, pages: list[int], *, arc: int, tess: str, dpi: int, lang: str,
            min_conf: float) -> tuple[list[Chapter], list[dict], list[str]]:
    # границы глав внутри хвоста — по закладкам PDF, где нумерация сбрасывается на 1
    toc = doc.get_toc()
    resets = set()
    for _lvl, title, pg in toc:
        if (pg - 1) in pages and re.match(r"^\s*0*1\s*$", title):
            resets.add(pg - 1)
    if not resets:
        resets.add(pages[0])

    chapters: list[Chapter] = []
    per_page: list[dict] = []
    review: list[str] = []
    cur: Chapter | None = None
    buf: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        for p in pages:
            text, words, mean = ocr_page(doc, p, tess, dpi, lang, wd)
            low = [(w, c) for w, c in words if 0 <= c < min_conf and re.search(r"\w", w)]
            per_page.append({"page": p + 1, "mean_conf": round(mean, 1),
                             "words": len(words), "low": len(low)})
            if low:
                review.append(f"### стр. {p + 1}  (средняя уверенность {mean:.0f}%)\n"
                              + ", ".join(f"`{w}`·{c:.0f}" for w, c in low))
            if p in resets:
                if cur is not None:
                    cur.body = "\n\n".join(buf)
                buf = []
                cur = Chapter(kind="chapter", label="", title="",
                              source_ref=f"pdf OCR p.{p + 1}")
                chapters.append(cur)
            buf.append(text)
        if cur is not None:
            cur.body = "\n\n".join(buf)

    # снять распознанный заголовок с начала каждой главы
    for ch in chapters:
        ps = [x for x in ch.body.split("\n\n") if x.strip()]
        for k in range(min(2, len(ps))):
            info = classify_heading(ps[k])
            if info and info["kind"] in ("chapter", "prologue", "interlude", "epilogue"):
                ch.kind = info["kind"] if info["kind"] != "chapter" else ch.kind
                ch.label = info["label"] or ch.label
                title = info["title"]
                drop = k + 1
                if not title and k + 1 < len(ps) and len(ps[k + 1]) < 70:
                    title = _trim_title(ps[k + 1])
                    drop = k + 2
                ch.title = title
                ps = ps[drop:]
                break
        ch.body = "\n\n".join(ps)
    return chapters, per_page, review


# ─────────────────────────── main ───────────────────────────

def main() -> None:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("--arc", type=int, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--volume", type=int, default=None)
    ap.add_argument("--phase", type=int, default=None)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--text-pages", default=None,
                    help="какие страницы брать из текстового слоя (по умолч. все, "
                         "кроме --ocr-pages)")
    ap.add_argument("--ocr-pages", default=None,
                    help="диапазон страниц без текстового слоя → OCR (напр. 1738-1830)")
    ap.add_argument("--ocr-only", action="store_true", help="только OCR-ветка")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--heading-gap", type=float, default=1.5,
                    help="на сколько pt заголовок крупнее основного кегля (по умолч. 1.5)")
    ap.add_argument("--tesseract", default=None, help="путь к tesseract.exe")
    ap.add_argument("--ocr-dpi", type=int, default=300)
    ap.add_argument("--ocr-lang", default="rus")
    ap.add_argument("--ocr-min-conf", type=float, default=60.0,
                    help="слова ниже этой уверенности → в _ocr_review.md")
    ap.add_argument("--side-story", default=None,
                    help="писать как побочную историю (в _pending), напр. \"One Day II\"")
    ap.add_argument("--read-after", default=None,
                    help="для --side-story: где читать, напр. 4:6 (арка:фаза)")
    ap.add_argument("--show-titles", action="store_true")
    args = ap.parse_args()

    doc = pymupdf.open(args.source)
    n = doc.page_count
    print(f"{args.source.name}: {n} страниц")

    ocr_idx = parse_ranges(args.ocr_pages, n) if args.ocr_pages else []
    if args.ocr_only:
        text_idx = []
    elif args.text_pages:
        text_idx = parse_ranges(args.text_pages, n)
    else:
        text_idx = [i for i in range(n) if i not in set(ocr_idx)]

    chapters: list[Chapter] = []
    image_pages: list[int] = []
    ocr_pages_report: list[dict] = []
    ocr_review: list[str] = []

    if text_idx:
        chapters, image_pages = extract_text_chapters(
            doc, text_idx, arc=args.arc, heading_gap=args.heading_gap)
        print(f"текстовый слой: страниц {len(text_idx)}, "
              f"блоков {len(chapters)}, страниц-картинок {len(image_pages)}")

    if ocr_idx:
        tess = find_tesseract(args.tesseract)
        print(f"OCR: {len(ocr_idx)} страниц, {tess}, {args.ocr_dpi} dpi, "
              f"lang={args.ocr_lang}")
        ocr_chs, ocr_pages_report, ocr_review = run_ocr(
            doc, ocr_idx, arc=args.arc, tess=tess, dpi=args.ocr_dpi,
            lang=args.ocr_lang, min_conf=args.ocr_min_conf)
        chapters.extend(ocr_chs)
        means = [r["mean_conf"] for r in ocr_pages_report]
        lows = sum(r["low"] for r in ocr_pages_report)
        allw = sum(r["words"] for r in ocr_pages_report)
        print(f"OCR: глав {len(ocr_chs)}, средняя уверенность "
              f"{sum(means) / len(means):.1f}%, слов ниже порога "
              f"{lows} из {allw} ({100 * lows / max(allw, 1):.1f}%)")

    for ch in chapters:
        ch.volume = args.volume
        ch.phase = args.phase
        ch.body = trim_scene_breaks(normalize_typography(ch.body))

    offset = args.offset
    prev_chapters: list[dict] = []
    if args.append and args.out and (args.out / "_manifest.json").exists():
        prev = json.loads((args.out / "_manifest.json").read_text("utf-8"))
        prev_chapters = prev.get("chapters", [])
        nums = [int(c["number"]) for c in prev_chapters
                if (c.get("number") or "").isdigit()]
        offset = max(nums) if nums else offset

    report = assign_numbers(chapters, offset=offset, order_offset=len(prev_chapters))
    rep = Reporter(args.show_titles)
    rep.table(chapters)
    rep.summary(chapters, report)

    if image_pages:
        print(f"страницы-иллюстрации: {compress_ranges(p + 1 for p in image_pages)}")
    ch_words = [c.words for c in chapters if c.kind == "chapter"]
    med = sorted(ch_words)[len(ch_words) // 2] if ch_words else 0
    short = [c.label or i for i, c in enumerate(chapters)
             if c.kind == "chapter" and c.words < max(350, med * 0.3)]
    long = [c.label or i for i, c in enumerate(chapters)
            if c.kind == "chapter" and med and c.words > med * 2.5]
    if short:
        print(f"! подозрительно короткие блоки (проверь разбиение): {short}")
    if long:
        print(f"! подозрительно длинные блоки (возможно, слиты соседние): {long}")

    if not args.out:
        print("\n(dry-run — ничего не записано; добавь --out)")
        return

    # ── побочная история (One Day II) → content/_pending, а не арка ──
    if args.side_story:
        from _common import frontmatter, paragraphs as _p
        pdir = args.out
        side_dir = pdir / "side"
        side_dir.mkdir(parents=True, exist_ok=True)
        slug = "arc-{}-{}".format(
            args.arc,
            re.sub(r"[^a-z0-9]+", "-",
                   args.side_story.lower().encode("ascii", "ignore").decode()).strip("-")
            or "story")
        for i, ch in enumerate(chapters, 1):
            meta = {"arc": args.arc, "type": "side", "title": ch.title,
                    "order_release": i}
            (side_dir / f"{slug}-{i:02d}.md").write_text(
                f"---\n{frontmatter(meta)}\n---\n\n"
                + "\n\n".join(_p(ch.body)) + "\n", encoding="utf-8")
        idx = pdir / "_index.json"
        reg = json.loads(idx.read_text("utf-8")) if idx.exists() else []
        reg = [e for e in reg if e.get("slug") != slug]
        ra = None
        if args.read_after and ":" in args.read_after:
            a, p = args.read_after.split(":", 1)
            ra = {"arc": int(a), "phase": int(p)}
        reg.append({"slug": slug, "title": args.side_story, "title_alt": "",
                    "title_orig": "", "type": "side", "parts": len(chapters),
                    "read_after": ra,
                    "source_file": f"PDF OCR стр. {ocr_idx[0] + 1}-{ocr_idx[-1] + 1}",
                    "status": "pending"})
        idx.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
        if ocr_review:
            (side_dir / f"{slug}_ocr_review.md").write_text(
                "# OCR: места для правки\n\n" + "\n\n".join(ocr_review), encoding="utf-8")
        print(f"\nпобочная «{args.side_story}»: {len(chapters)} частей → {side_dir}")
        return

    args.out.mkdir(parents=True, exist_ok=True)
    img_dir = args.out / "images"
    img_dir.mkdir(exist_ok=True)
    # иллюстрации-страницы → ближайшая предыдущая глава
    img_seq = max((int(m.group(1)) for f in img_dir.glob("i_*")
                   if (m := re.match(r"i_(\d+)", f.name))), default=0) if args.append else 0
    for p in image_pages:
        owner = None
        for ch in chapters:
            m = re.search(r"p\.(\d+)", ch.source_ref)
            if m and int(m.group(1)) <= p + 1:
                owner = ch
        img_seq += 1
        got = dump_page_images(doc, p, img_dir, f"i_{img_seq:03d}")
        if owner is not None and got:
            owner.illustrations.extend(got)
            owner.body += "\n\n" + "\n\n".join(f"@@IMAGE:{g}@@" for g in got)

    seen: dict[str, int] = {}
    for pc in prev_chapters:
        seen[pc["type"]] = seen.get(pc["type"], 0) + 1
    slugs: list[str] = []
    for ch in chapters:
        idx = seen.get(ch.kind, 0)
        seen[ch.kind] = idx + 1
        slugs.append(write_chapter(args.out, ch, args.arc, index=idx))

    prev_meta = {}
    if args.append and (args.out / "_manifest.json").exists():
        prev_meta = json.loads((args.out / "_manifest.json").read_text("utf-8"))
    merged = prev_chapters + manifest_rows(chapters, slugs=slugs)
    write_manifest_rows(args.out, merged, extra={
        "arc": args.arc, "generator": "pdf_to_md.py",
        "source": sorted(set(prev_meta.get("source") or []) | {args.source.name}),
        "ocr_pages": sorted(set(prev_meta.get("ocr_pages") or [])
                            | {r["page"] for r in ocr_pages_report}),
        "image_pages": sorted(set(prev_meta.get("image_pages") or [])
                              | {p + 1 for p in image_pages}),
        "images_total": img_seq,
    })
    if ocr_review:
        (args.out / "_ocr_review.md").write_text(
            "# OCR: места для разовой правки\n\n"
            "Слова с уверенностью ниже порога. Правится точечно по списку, "
            "а не вычиткой всего текста.\n\n" + "\n\n".join(ocr_review),
            encoding="utf-8")
        print(f"OCR-правка: {args.out / '_ocr_review.md'}")
    if ocr_pages_report:
        worst = sorted(ocr_pages_report, key=lambda r: r["mean_conf"])[:5]
        print("худшие страницы OCR:", [(r["page"], r["mean_conf"]) for r in worst])

    print(f"\nзаписано в {args.out}: {len(chapters)} файлов "
          f"(всего {len(merged)})")


if __name__ == "__main__":
    main()
