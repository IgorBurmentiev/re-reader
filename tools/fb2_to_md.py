#!/usr/bin/env python3
"""
fb2_to_md.py — конвертер FB2 в структуру проекта-читалки.

На выходе:
    out/
      001.md 002.md …            главы в Markdown с frontmatter
      images/i_001.jpg …         иллюстрации в оригинальном разрешении
      _manifest.json             метаданные: главы, картинки, привязка к абзацам

Два режима, выбираются автоматически:
  • структурный — тома 1–9: главы лежат <section> с <title>, внутри подглавы
    «1», «2», … Slug вида v04-c012 (вложенная структура ранобэ).
  • сканирующий — арки 7, 8: весь текст в одной-двух безымянных <section>,
    заголовки — абзацами (<p><strong>Глава 61: …</strong></p>,
    «Арка 8 — Глава N, "…"»), маркеры «Фаза N (веб-новелла)» там же.

Спойлер-безопасно: в консоль только цифры. Названия — с флагом --show-titles.

    python fb2_to_md.py "Том 4 Re_Zero.fb2" --arc 3 --volume 4 --out content/arc-03
    python fb2_to_md.py "Арка 7 … .fb2" --arc 7 --out content/arc-07
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path

try:
    from lxml import etree
except ImportError:
    sys.exit("Нужен lxml:  pip install lxml")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    Chapter, Reporter, SCENE_BREAK, assign_numbers, classify_heading,
    finalize_write, force_utf8_stdout, is_scene_break, normalize_typography,
    trim_scene_breaks,
)
from _common import _trim_title  # noqa: E402
import json  # noqa: E402

NS = {"fb": "http://www.gribuser.ru/xml/fictionbook/2.0",
      "l": "http://www.w3.org/1999/xlink"}
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}


def local(el) -> str:
    return etree.QName(el).localname


# ─────────────────────────── inline → markdown ───────────────────────────

def inline_md(el) -> str:
    parts = []
    if el.text:
        parts.append(el.text)
    for child in el:
        tag = local(child)
        inner = inline_md(child)
        if tag == "emphasis":
            parts.append(f"*{inner}*" if inner.strip() else inner)
        elif tag == "strong":
            parts.append(f"**{inner}**" if inner.strip() else inner)
        elif tag == "image":
            href = child.get(f"{{{NS['l']}}}href", "").lstrip("#")
            parts.append(f"\n\n@@IMAGE:{href}@@\n\n")
        else:
            parts.append(inner)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def plain(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def parse_notes(root) -> dict[str, str]:
    """<body name="notes"> → {id: текст примечания}. Ведущий повтор номера убираем."""
    out: dict[str, str] = {}
    for body in root.findall("fb:body", NS):
        if body.get("name") != "notes":
            continue
        for sec in body.findall(".//fb:section", NS):
            sid = sec.get("id")
            if not sid:
                continue
            txt = " ".join(plain(p) for p in sec.iter() if local(p) == "p").strip()
            txt = re.sub(r"^\s*\d+[.)]?\s+", "", txt)     # «1 Легендарный меч …»
            if txt:
                out[sid] = txt
    return out


def notes_block(sec, notes_map: dict[str, str]) -> str:
    """Собирает примечания, на которые ссылается секция, в хвостовой блок."""
    if not notes_map:
        return ""
    seen: list[tuple[str, str]] = []
    for a in sec.findall(".//fb:a", NS):
        if (a.get("type") or "") != "note":
            continue
        ref = (a.get(f"{{{NS['l']}}}href") or "").lstrip("#")
        num = re.sub(r"\D", "", plain(a)) or str(len(seen) + 1)
        if ref in notes_map and ref not in {r for r, _ in seen}:
            seen.append((ref, num))
    if not seen:
        return ""
    lines = ["<hr class='notes-rule' />", "**Примечания**"]
    for ref, num in seen:
        lines.append(f"{num}. {notes_map[ref]}")
    return "\n\n".join(lines)


def render_block(node, images: list[str]) -> str:
    tag = local(node)
    if tag == "p":
        md = inline_md(node).strip()
        # звёздочки/ромбики (в т.ч. в *курсиве*) — это разделитель сцен, не абзац
        if is_scene_break(md.strip("*_ ")):
            return SCENE_BREAK
        return md
    if tag == "subtitle":
        sub = inline_md(node).strip()
        return SCENE_BREAK if is_scene_break(sub.strip("*_ ")) else f"### {sub}"
    if tag == "empty-line":
        return SCENE_BREAK
    if tag == "image":
        href = node.get(f"{{{NS['l']}}}href", "").lstrip("#")
        if href:
            images.append(href)
        return f"@@IMAGE:{href}@@"
    if tag in ("epigraph", "cite", "poem"):
        lines = [inline_md(p).strip() for p in node.iter()
                 if local(p) in ("p", "v")]
        return "\n".join(f"> {x}" for x in lines if x)
    if tag == "section":
        out = []
        sub = section_title(node)
        if sub:
            out.append(f"## {sub}")
        out.append(render_section_body(node, images))
        return "\n\n".join(x for x in out if x.strip())
    return ""


def render_section_body(sec, images: list[str]) -> str:
    out = []
    for node in sec:
        if local(node) == "title":
            continue
        piece = render_block(node, images)
        if piece.strip():
            out.append(piece)
    return "\n\n".join(out)


def section_title(sec) -> str:
    t = sec.find("fb:title", NS)
    if t is None:
        return ""
    return re.sub(r"\s+", " ",
                  " ".join(plain(p) for p in t.iter() if local(p) == "p")).strip()


# ─────────────────────────── режим 1: структурный ───────────────────────────

def build_structured(body, *, volume: int | None, notes_map: dict[str, str] | None = None):
    chapters: list[Chapter] = []
    notes_map = notes_map or {}
    for i, sec in enumerate(body.findall("fb:section", NS)):
        title = section_title(sec)
        images: list[str] = []
        text = render_section_body(sec, images)
        nb = notes_block(sec, notes_map)
        if nb:
            text = (text + "\n\n" + nb).strip()
        # <image> внутри <p> помечается @@IMAGE@@ в тексте, но в images не попадает
        for m in re.findall(r"@@IMAGE:([^@]+)@@", text):
            if m not in images:
                images.append(m)

        info = classify_heading(title)
        if info and info["kind"] != "phase":
            kind, label, ttl = info["kind"], info["label"], info["title"]
        else:
            kind, label, ttl = "chapter", "", _trim_title(title)
            m = re.match(r"^\s*глава\s+(\d+)\b[.\s—:-]*(.*)$", title, re.I)
            if m:
                label, ttl = m.group(1), _trim_title(m.group(2))
        if "иллюстрац" in title.lower():
            kind, label = "extra", ""

        # пустые технические секции (титул тома, разделитель) — пропускаем
        if not text.strip() and not images and kind not in ("prologue", "epilogue",
                                                            "interlude"):
            continue

        chapters.append(Chapter(
            kind=kind, label=label, title=ttl, body=text, volume=volume,
            illustrations=images, source_ref=f"section {i}",
        ))
    return chapters


# ─────────────────────────── режим 2: сканирующий ───────────────────────────

_FLAT_TAGS = ("p", "subtitle", "empty-line", "image")


def _is_heading_p(node) -> tuple[bool, str]:
    """<p> целиком в <strong>/<b>, либо короткая строка-заголовок."""
    txt = plain(node)
    if not txt or len(txt) > 120:
        return False, txt
    kids = [k for k in node if local(k) not in ("image",)]
    wrapped = len(kids) == 1 and local(kids[0]) in ("strong",) and not (node.text or "").strip()
    return (wrapped or bool(classify_heading(txt))), txt


# строки-«шапки», которые надо снять с начала главы («Перевод, редактура: …»)
_CREDIT_RE = re.compile(r"^\s*(база|перевод\w*|редактура|редактор|источник|тайпсет|"
                        r"оформл\w*|вычитка|фанарт|колор\w*|клин\w*|эдит\w*)"
                        r"\b[^:\n]{0,40}:|^\s*(https?://|vk\.com/|t\.me/)\S", re.I)
# из них в поля идут только «полезные»; колор/тайпсет/фанарт — просто снимаются
_CREDIT_KEEP = re.compile(r"^\s*(база|перевод|редактура|редактор|вычитка|источник)"
                          r"|^\s*(https?://|vk\.com|t\.me)", re.I)


def _credit_value(txt: str) -> str:
    t = txt.strip()
    if re.match(r"https?://|vk\.com|t\.me", t, re.I):
        return re.search(r"(https?://\S+|(?:vk\.com|t\.me)/\S+)", t).group(1)
    v = t.split(":", 1)[1].strip() if ":" in t else t
    return re.sub(r"^\s*[-–—]\s*", "", v).strip(" .,;")


def build_flat(body, *, volume: int | None, default_phase: int | None,
               notes_map: dict[str, str] | None = None):
    blocks = [el for el in body.iter() if local(el) in _FLAT_TAGS]
    chapters: list[Chapter] = []
    cur: Chapter | None = None
    buf: list[str] = []
    images_cur: list[str] = []
    phase = default_phase
    front_skipped = 0
    credits = {"translator": "", "source": ""}
    num2note = {re.sub(r"\D", "", k): v for k, v in (notes_map or {}).items()}

    expect_title = False   # предыдущий блок — заголовок без названия

    def flush():
        nonlocal buf, images_cur
        if cur is not None:
            cur.body = "\n\n".join(x for x in buf if x.strip())
            cur.illustrations = images_cur
        buf, images_cur = [], []

    for el in blocks:
        tag = local(el)
        if tag == "image":
            href = el.get(f"{{{NS['l']}}}href", "").lstrip("#")
            if cur is not None and href:
                images_cur.append(href)
                buf.append(f"@@IMAGE:{href}@@")
            expect_title = False
            continue
        if tag == "empty-line":
            if cur is not None and not expect_title:
                buf.append(SCENE_BREAK)
            continue
        txt = plain(el)
        if not txt:
            continue
        if tag == "p" and len(txt) < 120 and _CREDIT_RE.match(txt):
            if not _CREDIT_KEEP.match(txt):
                continue                       # колор/тайпсет/клин — просто снять
            low = txt.lower()
            val = _credit_value(txt)
            # шапка перевода: у главы — своя (арка 8), общая — до первой главы
            tgt = cur if (cur is not None and len(buf) <= 6) else None
            is_src = bool(re.search(r"http|vk\.com|t\.me", low)) or \
                low.startswith(("база", "источник"))
            if tgt is not None:
                if is_src:
                    tgt.source = tgt.source or val
                elif val and val not in tgt.translator.split("; "):
                    tgt.translator = (tgt.translator + "; " + val).strip("; ")
            else:
                key = "source" if is_src else "translator"
                if val and val not in credits[key].split("; "):
                    credits[key] = (credits[key] + "; " + val).strip("; ")
            continue
        info = classify_heading(txt)
        is_head, _ = _is_heading_p(el) if tag == "p" else (False, txt)

        # название отдельной строкой сразу после «Глава N» без названия
        if expect_title and cur is not None and not cur.title:
            expect_title = False
            if is_head and not info and not re.fullmatch(r"\d+", txt) and len(txt) < 80:
                cur.title = _trim_title(txt)
                continue

        if info and info["kind"] == "phase":
            phase = int(info["label"])
            continue
        if is_head and info and info["kind"] != "phase":
            flush()
            cur = Chapter(kind=info["kind"], label=info["label"],
                          title=info["title"], volume=volume, phase=phase,
                          source_ref="flat-scan")
            chapters.append(cur)
            expect_title = not info["title"]
            continue
        expect_title = False
        if cur is None:
            front_skipped += 1
            continue
        buf.append(inline_md(el).strip() if tag == "p" else f"### {txt}")
    flush()
    for c in chapters:
        c.translator = c.translator or credits["translator"]
        c.source = c.source or credits["source"]
        used = [n for n in dict.fromkeys(re.findall(r"\[(\d{1,3})\]", c.body))
                if n in num2note]
        if used:
            c.body += "\n\n<hr class='notes-rule' />\n\n**Примечания**\n\n" + \
                "\n\n".join(f"{n}. {num2note[n]}" for n in used)
    return chapters, front_skipped


# ─────────────────────────── main ───────────────────────────

def main() -> None:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("--arc", type=int, required=True)
    ap.add_argument("--volume", type=int, default=None)
    ap.add_argument("--phase", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--offset", type=int, default=0, help="сдвиг сквозной нумерации глав")
    ap.add_argument("--append", action="store_true",
                    help="дописать к существующему out (продолжить нумерацию по _manifest.json)")
    ap.add_argument("--mode", choices=("auto", "structured", "flat"), default="auto")
    ap.add_argument("--nested-slug", action="store_true",
                    help="slug вида v04-c012 (вложенная структура ранобэ)")
    ap.add_argument("--show-titles", action="store_true")
    args = ap.parse_args()

    parser = etree.XMLParser(huge_tree=True, recover=True)
    root = etree.parse(str(args.source), parser).getroot()

    book_title = root.findtext(".//fb:book-title", default="", namespaces=NS)
    ann_el = root.find(".//fb:title-info/fb:annotation", NS)
    annotation = plain(ann_el) if ann_el is not None else ""
    # переводчиков в <title-info> может быть несколько — собираем всех
    trs = []
    for tr in root.findall(".//fb:title-info/fb:translator", NS):
        nick = tr.findtext("fb:nickname", "", NS)
        name = " ".join(x for x in (tr.findtext("fb:first-name", "", NS),
                                    tr.findtext("fb:last-name", "", NS)) if x)
        v = (nick or name).strip()
        if v and v not in trs:
            trs.append(v)
    translator = "; ".join(trs)

    binaries: dict[str, tuple[bytes, str]] = {}
    for b in root.findall(".//fb:binary", NS):
        try:
            binaries[b.get("id")] = (base64.b64decode(b.text or ""),
                                     b.get("content-type", "image/jpeg"))
        except Exception:
            pass

    bodies = [b for b in root.findall("fb:body", NS) if b.get("name") != "notes"]
    if not bodies:
        sys.exit("Не найден основной <body>")
    body = bodies[0]
    notes_map = parse_notes(root)

    top = body.findall("fb:section", NS)
    titled = sum(1 for s in top if section_title(s))
    mode = args.mode
    if mode == "auto":
        mode = "structured" if (len(top) >= 3 and titled >= len(top) * 0.6) else "flat"

    front_skipped = 0
    if mode == "structured":
        chapters = build_structured(body, volume=args.volume, notes_map=notes_map)
    else:
        chapters, front_skipped = build_flat(
            body, volume=args.volume, default_phase=args.phase, notes_map=notes_map)

    for ch in chapters:
        ch.phase = ch.phase or args.phase
        ch.translator = ch.translator or translator
        ch.body = trim_scene_breaks(normalize_typography(ch.body))

    offset = args.offset
    order_offset = 0
    if args.append and args.out and (args.out / "_manifest.json").exists():
        prev = json.loads((args.out / "_manifest.json").read_text("utf-8"))
        prev_rows = prev.get("chapters", [])
        order_offset = len(prev_rows)
        nums = [int(c["number"]) for c in prev_rows if (c.get("number") or "").isdigit()]
        offset = max(nums) if nums else offset
        print(f"append: продолжаю нумерацию с {offset + 1}")

    report = assign_numbers(chapters, offset=offset, order_offset=order_offset)

    print(f"книга: {book_title}   (режим: {mode})")
    if front_skipped:
        print(f"преамбула до первой главы пропущена: {front_skipped} абз.")
    rep = Reporter(args.show_titles)
    rep.table(chapters)
    rep.summary(chapters, report, binaries=len(binaries))

    if not args.out:
        print("\n(dry-run — ничего не записано; добавь --out)")
        return

    # binaries {id: (bytes, ctype)} → {name: bytes} с расширением по content-type
    def bin_name(bid: str, ctype: str) -> str:
        return bid if "." in bid else f"{bid}.{EXT.get(ctype, 'jpg')}"
    id2name = {bid: bin_name(bid, ct) for bid, (_d, ct) in binaries.items()}
    images = {id2name[bid]: data for bid, (data, _ct) in binaries.items()}
    for c in chapters:
        c.illustrations = [id2name.get(x, x) for x in c.illustrations]
        for bid, nm in id2name.items():
            c.body = c.body.replace(f"@@IMAGE:{bid}@@", f"@@IMAGE:{nm}@@")
    referenced = {im for c in chapters for im in c.illustrations}
    orphans = set(images) - referenced

    n, total = finalize_write(
        args.out, chapters, args.arc, images=images, generator="fb2_to_md.py",
        sources=[args.source.name], append=args.append, nested=args.nested_slug,
        orphan_images=orphans,
        extra={"volume": args.volume, "book_title": book_title,
               "annotation": annotation, "mode": mode})
    print(f"\nзаписано в {args.out}: +{n} файлов (всего {total}), "
          f"{len(images)} иллюстраций (в галерею тома без привязки: {len(orphans)})")


if __name__ == "__main__":
    main()
