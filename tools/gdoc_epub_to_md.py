"""Одиночная побочная история из epub, экспортированного Google Docs → content/extra.

Формат Google Docs отличается от сборника (`extra_epub_to_md.py`): вся история —
один `..xhtml` без toc.ncx, оформление задано CSS-классами (`.c35{font-style:
italic}`), сноски — `<sup><a href="#ftntN">[N]</a></sup>` в тексте и блоки
`<div><p><a id="ftntN">[N]</a> текст</p></div>` в самом конце. Титры
переводчиков стоят в хвосте документа, после «⟅ КОНЕЦ ⟆».

Запись встаёт на место уже существующей строки реестра `_index.json`
(обычно заглушки «нет перевода»): `--replace` — её slug; категория, место
в хронологии (read_after) и теги берутся из неё, если не заданы явно.

    python tools/gdoc_epub_to_md.py "sources/side/X.epub" --slug new-slug \
        --replace old-slug --title "…" --translator "…" [--drop-image N ...]

Печатает только статистику (без текста — спойлеры).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    SCENE_BREAK, force_utf8_stdout, is_scene_break, normalize_typography,
    trim_scene_breaks, write_text_lf,
)

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

END_RE = re.compile(r"^⟅?\s*КОНЕЦ\s*⟆?$", re.I)
DIVIDER_RE = re.compile(r"^(?:[×x*※]\s*){2,}$")


def css_classes(html: str) -> tuple[set[str], set[str]]:
    """Имена классов с курсивом и с жирным начертанием из <style> документа."""
    italic, bold = set(), set()
    for name, decl in re.findall(r"\.(c\d+)\{([^}]*)\}", html):
        if "font-style:italic" in decl:
            italic.add(name)
        if "font-weight:700" in decl:
            bold.add(name)
    return italic, bold


def _esc(s: str) -> str:
    return re.sub(r"([*_`\[\]\\])", r"\\\1", s)


def inline_md(p: Tag, italic: set[str], bold: set[str]) -> str:
    """Текст абзаца с *курсивом*/**жирным** и [^N] вместо ссылок на сноски."""
    out: list[str] = []
    for node in p.descendants:
        if isinstance(node, Tag) and node.name == "a" and \
                (node.get("href") or "").startswith("#ftnt"):
            n = re.search(r"\d+", node["href"])
            out.append(f"[^{n.group()}]" if n else "")
            continue
        if not isinstance(node, NavigableString):
            continue
        if node.find_parent("a", href=re.compile(r"^#ftnt")):
            continue
        # xhtml отформатирован с отступами: перевод строки + отступ между тегами —
        # это разметка файла, а не пробел в тексте (настоящие пробелы Google Docs
        # кладёт внутрь span)
        text = re.sub(r"^\n\s*|\n\s*$", "", str(node))
        if not text.strip():
            out.append(text)
            continue
        span = node.find_parent("span")
        cls = set(span.get("class") or []) if span else set()
        mark = ("**" if cls & bold else "") + ("*" if cls & italic else "")
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        core = _esc(text.strip())
        out.append(f"{lead}{mark}{core}{mark[::-1]}{trail}" if mark else
                   f"{lead}{core}{trail}")
    s = re.sub(r"\s+", " ", "".join(out)).strip()
    s = re.sub(r"(?<=[^\s*])\*\*(?=[^\s*])", "", s)   # «*а**б*» — соседние курсивные span
    s = re.sub(r"\s+(\[\^\d+\])", r"\1", s)           # сноска прилипает к слову
    return normalize_typography(s)


def convert(epub: Path, drop_images: set[int]) -> dict:
    with zipfile.ZipFile(epub) as z:
        names = z.namelist()
        doc = next(n for n in names if n.endswith(".xhtml") and "nav" not in n.lower())
        html = z.read(doc).decode("utf-8")
        base = doc.rsplit("/", 1)[0] + "/" if "/" in doc else ""
        italic, bold = css_classes(html)
        soup = BeautifulSoup(html, "lxml")

        md: list[str] = []
        images: list[tuple[str, bytes]] = []
        notes: dict[str, str] = {}
        credits: list[str] = []
        ended = False
        seen_title = False

        for el in soup.body.find_all(recursive=False):
            text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
            if el.name == "div":
                a = el.find("a", id=re.compile(r"^ftnt\d+$"))
                if a:
                    n = re.search(r"\d+", a["id"]).group()
                    a.decompose()
                    p = el.find("p") or el
                    notes[n] = inline_md(p, italic, bold)
                continue
            imgs = el.find_all("img")
            for img in imgs:
                idx = int(re.search(r"(\d+)", Path(img["src"]).stem).group(1))
                if idx in drop_images:
                    continue
                images.append((img["src"], z.read(base + img["src"])))
                md.append(f"@@IMAGE:{len(images) - 1}@@")
            if imgs or el.name == "hr" or not text:
                continue
            if el.name.startswith("h") and not seen_title:
                seen_title = True
                continue
            if ended:
                credits.append(text)
                continue
            if END_RE.match(text):
                ended = True
                # строка-повтор названия прямо перед «КОНЕЦ» — оформление
                if md and not md[-1].startswith("@@") and "«" in md[-1] and len(md[-1]) < 80:
                    md.pop()
                continue
            if DIVIDER_RE.match(text) or is_scene_break(text):
                # разделитель сразу под заголовком (до первого текста) — оформление шапки
                if any(not b.startswith("@@") for b in md):
                    md.append(SCENE_BREAK)
                continue
            md.append(inline_md(el, italic, bold))

    body = trim_scene_breaks("\n\n".join(md))
    if notes:
        body += "\n\n" + "\n\n".join(f"[^{n}]: {t}" for n, t in
                                     sorted(notes.items(), key=lambda x: int(x[0])))
    return {"body": body, "images": images, "credits": credits, "notes": len(notes)}


def main() -> None:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub", type=Path)
    ap.add_argument("--out", type=Path, default=Path("content/extra"))
    ap.add_argument("--slug", required=True)
    ap.add_argument("--replace", help="slug строки реестра, которую заменяет история")
    ap.add_argument("--title", required=True)
    ap.add_argument("--title-jp", default=None)
    ap.add_argument("--translator", default="")
    ap.add_argument("--fanart", default="")
    ap.add_argument("--drop-image", type=int, action="append", default=[],
                    help="номер imageN.* в epub, который не нужен (разделители и т.п.)")
    args = ap.parse_args()

    res = convert(args.epub, set(args.drop_image))
    index_path = args.out / "_index.json"
    registry = json.loads(index_path.read_text(encoding="utf-8"))
    old_slug = args.replace or args.slug
    pos = next((i for i, r in enumerate(registry) if r["slug"] == old_slug), None)
    old = registry[pos] if pos is not None else {}

    img_dir = args.out / "images"
    nums = [int(m.group(1)) for p in img_dir.iterdir()
            if (m := re.match(r"i_(\d+)\.", p.name))]
    nxt = max(nums, default=0) + 1
    body = res["body"]
    for k, (src, data) in enumerate(res["images"]):
        name = f"i_{nxt + k:03d}{Path(src).suffix.lower()}"
        (img_dir / name).write_bytes(data)
        body = body.replace(f"@@IMAGE:{k}@@", f"![](./images/{name})")

    ra = old.get("read_after") or {}
    fm = {
        "title": args.title,
        "title_jp": args.title_jp if args.title_jp is not None else old.get("title_jp", ""),
        "category": old.get("category", "side"),
        "status": "ok",
        "read_after_arc": ra.get("arc"),
        "read_after_container": ra.get("container"),
        "tags": old.get("tags", []),
        "translator": args.translator,
        "fanart": args.fanart,
        "source_ref": args.epub.name,
    }
    lines = ["---"]
    for k, v in fm.items():
        if v in (None, "") and k not in ("title",):
            continue
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    write_text_lf(args.out / f"{args.slug}.md", "\n".join(lines) + "\n\n" + body + "\n")

    if args.replace and args.replace != args.slug:
        stale = args.out / f"{args.replace}.md"
        if stale.exists():
            stale.unlink()

    words = len(re.findall(r"\w+", body))
    row = {**old, "slug": args.slug, "title": args.title, "title_jp": fm["title_jp"],
           "category": fm["category"], "tags": fm["tags"],
           "translator": args.translator, "fanart": args.fanart,
           "parts": 1, "part_slugs": [args.slug], "status": "ok", "words": words}
    if pos is None:
        registry.append(row)
    else:
        registry[pos] = row
    index_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")

    paras = body.count("\n\n") + 1
    print(f"{args.slug}: {words} слов, ~{paras} блоков, картинок {len(res['images'])} "
          f"(i_{nxt:03d}…), сносок {res['notes']}, строк титров {len(res['credits'])}")
    for c in res["credits"]:
        print("  титры:", c)


if __name__ == "__main__":
    main()
