#!/usr/bin/env python3
"""
epub_to_md.py — конвертер EPUB в структуру проекта-читалки.

Один вход — один или несколько .epub, один выход:
    out/
      001.md 002.md … prologue-00.md interlude-01.md   главы с frontmatter
      images/i_001.jpg …                               иллюстрации в оригинале
      _manifest.json                                   метаданные + сверка с TOC

Ключевое (из ТЗ §4, §6.2):
  • идём по SPINE, а не по toc.ncx — оглавление в этих файлах часто неполное
    (арка 10: первая фаза в ncx не попала). ncx/nav используем только для сверки.
  • глава может быть размазана по нескольким файлам spine — файлы без своего
    заголовка приклеиваются к предыдущей главе.
  • заголовок бывает <h1..6> (арка 9) или <p class="block_2"> (арка 10),
    название — в том же блоке или отдельной строкой под номером (арка 10 фаза 2).
  • номер главы — строка: 2.5, 54B, 123 (A). number — сквозной счётчик,
    label — как в источнике; дубль+пропуск = сдвиг, глава не теряется.
  • иллюстрации не вшиваются: @@IMAGE:name@@ в теле → отдельный файл + манифест.
  • в консоль только цифры; названия — с флагом --show-titles.

Примеры:
  # арка 5 — один файл, по главе на spine-документ
  python epub_to_md.py "5 арка.epub" --arc 5 --out content/arc-05

  # арка 10, первая часть — заголовки в <p>, две фазы в одном файле
  python epub_to_md.py "Арка 10 ... .epub" --arc 10 --out content/arc-10

  # арка 10, онгоинг — папка из отдельных .epub, порядок по префиксу имени
  python epub_to_md.py sources/wn/arc10/arc10_ongoing --arc 10 --phase 3 \
      --out content/arc-10 --append --order-from-filename
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from bs4 import BeautifulSoup
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    sys.exit("Нужен beautifulsoup4:  pip install beautifulsoup4 lxml")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    CIRCLED_TO_INT, Chapter, Reporter, SCENE_BREAK, assign_numbers,
    classify_heading, force_utf8_stdout, is_cjk_only, is_scene_break,
    manifest_rows, normalize_typography, trim_scene_breaks, write_chapter,
    write_manifest_rows,
)
from _common import _trim_title  # noqa: E402

XHTML = "{http://www.w3.org/1999/xhtml}"
NCX = "{http://www.daisy.org/z3986/2005/ncx/}"


# ─────────────────────────── распаковка EPUB ───────────────────────────

class Epub:
    def __init__(self, path: Path):
        self.path = path
        self.zip = zipfile.ZipFile(path)
        self._names = {n.lower(): n for n in self.zip.namelist()}
        opf_path = self._opf_path()
        self.opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""
        opf = ET.fromstring(self.zip.read(opf_path))
        ns = {"o": opf.tag.split("}")[0].strip("{")} if "}" in opf.tag else {}

        self.meta = self._read_meta(opf, ns)
        self.manifest: dict[str, dict] = {}
        for it in opf.iter():
            if it.tag.endswith("}item") or it.tag == "item":
                self.manifest[it.get("id")] = {
                    "href": it.get("href"), "type": it.get("media-type") or "",
                    "props": it.get("properties") or "",
                }
        self.spine = [it.get("idref") for it in opf.iter()
                      if it.tag.endswith("}itemref") or it.tag == "itemref"]

    def all_images(self) -> dict[str, bytes]:
        """Все картинки из manifest (в т.ч. не привязанные ни к одной главе —
        такие уходят в галерею тома, ТЗ §6.3)."""
        out: dict[str, bytes] = {}
        for it in self.manifest.values():
            if it["type"].startswith("image"):
                real = self._resolve(it["href"])
                if real:
                    out[real.rsplit("/", 1)[-1]] = self.zip.read(real)
        return out

    def _opf_path(self) -> str:
        cont = self.zip.read("META-INF/container.xml").decode("utf-8", "replace")
        return re.search(r'full-path="([^"]+)"', cont).group(1)

    def _read_meta(self, opf, ns) -> dict:
        m = {"title": "", "creator": "", "language": ""}
        for el in opf.iter():
            tag = el.tag.rsplit("}", 1)[-1]
            if tag in m and el.text and not m[tag]:
                m[tag] = el.text.strip()
        return m

    def _resolve(self, href: str) -> str | None:
        href = re.sub(r"#.*$", "", href)
        for cand in (f"{self.opf_dir}/{href}" if self.opf_dir else href, href):
            cand = re.sub(r"[^/]+/\.\./", "", cand)
            if cand.lower() in self._names:
                return self._names[cand.lower()]
        tail = href.rsplit("/", 1)[-1].lower()
        for low, real in self._names.items():
            if low.endswith("/" + tail) or low == tail:
                return real
        return None

    def read_text(self, idref: str) -> str | None:
        it = self.manifest.get(idref)
        if not it:
            return None
        real = self._resolve(it["href"])
        if not real:
            return None
        return self.zip.read(real).decode("utf-8", "replace")

    def spine_basename(self, idref: str) -> str:
        it = self.manifest.get(idref, {})
        return (it.get("href") or idref).rsplit("/", 1)[-1]

    # ── картинки ──
    def image_bytes(self, src_href: str, base_href: str) -> tuple[str, bytes] | None:
        base_dir = base_href.rsplit("/", 1)[0] if "/" in base_href else ""
        raw = re.sub(r"#.*$", "", src_href)
        joined = f"{base_dir}/{raw}" if base_dir else raw
        for cand in (joined, raw):
            while "/../" in cand:
                cand = re.sub(r"[^/]+/\.\./", "", cand, count=1)
            real = self._resolve(cand)
            if real:
                return real.rsplit("/", 1)[-1], self.zip.read(real)
        return None

    # ── сверка: плоский список меток TOC ──
    def toc_labels(self) -> list[str]:
        for idref, it in self.manifest.items():
            if it["type"] == "application/x-dtbncx+xml":
                real = self._resolve(it["href"])
                if not real:
                    continue
                root = ET.fromstring(self.zip.read(real))
                out = []
                for np in root.iter(f"{NCX}navPoint"):
                    txt = "".join(t.text or "" for t in np.iter(f"{NCX}text"))
                    out.append(re.sub(r"\s+", " ", txt).strip())
                return [x for x in out if x]
        for idref, it in self.manifest.items():
            if "nav" in it["props"]:
                real = self._resolve(it["href"])
                soup = BeautifulSoup(self.zip.read(real), "lxml")
                nav = soup.find("nav") or soup
                return [re.sub(r"\s+", " ", a.get_text(" ", strip=True))
                        for a in nav.find_all("a") if a.get_text(strip=True)]
        return []


# ─────────────────────────── разбор одного XHTML ───────────────────────────

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
# один CSS-класс токеном: block_ / block_2 / block_29 (calibre), либо явные title/head/chapter
_HEADING_CLASS_RE = re.compile(r"^(?:block_\d*|chap\w*|title\w*|head\w*|section\w*|caption)$", re.I)


def _is_heading_class(el) -> bool:
    return any(_HEADING_CLASS_RE.match(c) for c in el.get("class", []))


def _clean_line(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _looks_like_toc(leaf, soup) -> bool:
    """Страница-оглавление: сплошь короткие строки-ссылки, без прозы."""
    if soup.find(attrs={"epub:type": re.compile("toc")}) or soup.find("nav"):
        return True
    texts = [_clean_line(el) for el in leaf if el.name not in ("img", "image")]
    texts = [t for t in texts if t]
    if len(texts) < 4:
        return False
    long_lines = sum(1 for t in texts if len(t.split()) > 12)
    headingish = sum(1 for t in texts if classify_heading(t))
    return long_lines == 0 and headingish >= 3


def parse_doc(html_text: str, epub: Epub, base_href: str):
    """Возвращает (heading_info | None, body_markdown, [image_names], {img_bytes}).

    heading_info присутствует, только если документ НАЧИНАЕТСЯ с заголовка;
    иначе это продолжение предыдущей главы.
    """
    soup = BeautifulSoup(html_text, "lxml")
    body = soup.body or soup
    for junk in body.select("script, style"):
        junk.decompose()

    blocks = [el for el in body.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "blockquote", "img", "image"],
        recursive=True)]
    # оставляем только «листовые» блоки (без вложенных блоков), чтобы не дублировать
    leaf = []
    for el in blocks:
        if el.name in ("img", "image"):
            leaf.append(el)
            continue
        if el.find(["p", "div", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"],
                   recursive=False):
            continue
        leaf.append(el)

    if _looks_like_toc(leaf, soup):
        return None, "", [], {}

    heading = None
    start = 0
    # ── поиск заголовка среди первых значимых блоков ──
    probe = 0
    for i, el in enumerate(leaf):
        if el.name in ("img", "image"):
            continue
        txt = _clean_line(el)
        if not txt:
            continue
        probe += 1
        is_h = el.name in _HEADING_TAGS or _is_heading_class(el) or i == 0
        info = classify_heading(txt) if (is_h and len(txt) <= 160) else None
        if info and info["kind"] != "phase":
            heading = info
            start = i + 1
            # название отдельной строкой под номером (арка 10: заголовок = только
            # «ГЛАВА N», название идёт следующим абзацем, за ним японский подзаголовок)
            if not heading["title"]:
                for j in range(start, min(start + 4, len(leaf))):
                    cand = _clean_line(leaf[j])
                    if not cand or is_cjk_only(cand) or is_scene_break(cand):
                        start = j + 1
                        continue
                    if len(cand) <= 110 and len(cand.split()) <= 14:
                        heading["title"] = _trim_title(cand)
                        start = j + 1
                    break
            break
        if probe >= 3:            # заголовок бывает только в самом начале
            break

    # ── тело ──
    md: list[str] = []
    images: list[str] = []
    for el in leaf[start:]:
        if el.name in ("img", "image"):
            src = el.get("src") or el.get("href") or el.get(f"{XHTML}href") or ""
            got = epub.image_bytes(src, base_href) if src else None
            if got:
                name = got[0]
                if name not in images:
                    images.append(name)
                md.append(f"@@IMAGE:{name}@@")
                el._saved = got                       # noqa: give bytes back to caller
            continue
        txt = _clean_line(el)
        if not txt:
            continue
        if is_scene_break(txt):
            md.append(SCENE_BREAK)
            continue
        if is_cjk_only(txt):
            continue
        if el.name == "blockquote":
            md.append("\n".join(f"> {ln}" for ln in txt.split("\n")))
        else:
            md.append(txt)

    # собрать байты картинок для сохранения
    img_bytes: dict[str, bytes] = {}
    for el in body.find_all(["img", "image"]):
        if getattr(el, "_saved", None):
            img_bytes[el._saved[0]] = el._saved[1]

    return heading, "\n\n".join(md), images, img_bytes


# ─────────────────────────── сборка глав из spine ───────────────────────────

def build_chapters(epub: Epub, *, arc: int, default_phase: int | None,
                   filename_hint: dict | None = None):
    chapters: list[Chapter] = []
    all_images: dict[str, bytes] = {}
    cur: Chapter | None = None
    phase = default_phase
    skipped_front = 0

    for idref in epub.spine:
        html_text = epub.read_text(idref)
        if html_text is None:
            continue
        base_href = epub.manifest[idref]["href"]
        heading, body, imgs, img_bytes = parse_doc(html_text, epub, base_href)
        all_images.update(img_bytes)
        basename = epub.spine_basename(idref)

        # фаза-разделитель как отдельный документ
        if heading is None:
            info = classify_heading(_first_line(html_text))
            if info and info["kind"] == "phase":
                phase = int(info["label"])
                continue

        words = len(body.split())
        if heading is None:
            if cur is None:
                # преамбула до первой главы (обложка, оглавление) — пропускаем
                skipped_front += 1
                continue
            if words == 0 and not imgs:
                continue
            cur.body += ("\n\n" if cur.body else "") + body
            for im in imgs:
                if im not in cur.illustrations:
                    cur.illustrations.append(im)
            cur.source_ref += f" +{basename}"
            continue

        if heading["kind"] == "phase":
            phase = int(heading["label"])
            continue

        # новый логический блок
        cur = Chapter(
            kind=heading["kind"], label=heading["label"], title=heading["title"],
            body=body, phase=phase, illustrations=list(imgs),
            source_ref=basename,
        )
        if filename_hint:
            cur.label = filename_hint.get("label", cur.label) or cur.label
            if filename_hint.get("kind"):
                cur.kind = filename_hint["kind"]
        chapters.append(cur)

    return chapters, all_images, skipped_front


def _first_line(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "lxml")
    for el in (soup.body or soup).find_all(["h1", "h2", "h3", "p", "div"]):
        t = _clean_line(el)
        if t:
            return t
    return ""


_FN_RE = re.compile(r"^\s*(\d+)[ _\-]+\d+[ _\-](\d+|interlude\d*|prologue\d*)", re.I)


def filename_hint(path: Path) -> dict:
    """'1_10-25.epub' → chapter 25, order 1;  '5_10-interlude3.epub' → interlude."""
    m = re.match(r"^\s*(\d+)[ _\-]+\d+[ _\-](.+?)\.epub$", path.name, re.I)
    if not m:
        return {}
    order, tail = int(m.group(1)), m.group(2).lower()
    if "interlude" in tail:
        return {"order": order, "kind": "interlude", "label": re.sub(r"\D", "", tail)}
    if "prologue" in tail or "пролог" in tail:
        return {"order": order, "kind": "prologue", "label": ""}
    digits = re.sub(r"\D", "", tail)
    return {"order": order, "kind": "chapter", "label": digits}


# ─────────────────────────── карантин побочных (ТЗ §6.4) ───────────────────────────

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _slugify_lat(s: str) -> str:
    s = "".join(_TRANSLIT.get(ch, ch) for ch in s.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "story"


def _write_pending(pdir: Path, arc: int, pending: list[Chapter],
                   images: dict[str, bytes] | None = None) -> None:
    side_dir = pdir / "side"
    side_dir.mkdir(parents=True, exist_ok=True)
    images = images or {}
    used_imgs = {im for ch in pending for im in ch.illustrations}
    if used_imgs:
        (side_dir / "images").mkdir(exist_ok=True)
        for im in used_imgs:
            if im in images:
                (side_dir / "images" / im).write_bytes(images[im])
    idx_path = pdir / "_index.json"
    registry = json.loads(idx_path.read_text("utf-8")) if idx_path.exists() else []
    known = {e["slug"] for e in registry}

    # группируем части одной истории по названию без кружка ①②③
    groups: dict[str, list[Chapter]] = {}
    for ch in pending:
        key = re.sub(r"\s*[①②③④⑤⑥⑦⑧⑨⑩]\s*$", "", ch.title).strip().lower()
        groups.setdefault(key, []).append(ch)

    from _common import frontmatter, paragraphs as _p
    for key, parts in groups.items():
        base_title = re.sub(r"\s*[①②③④⑤⑥⑦⑧⑨⑩]\s*$", "", parts[0].title).strip()
        slug = f"arc-{arc:02d}-{_slugify_lat(base_title)}"
        for i, ch in enumerate(parts, 1):
            fn = f"{slug}-{i:02d}.md" if len(parts) > 1 else f"{slug}.md"
            meta = {"arc": arc, "type": ch.kind, "phase": ch.phase,
                    "title": ch.title, "order_release": ch.order_release}
            body = re.sub(r"@@IMAGE:([^@]+)@@", r"![](./images/\1)", ch.body)
            (side_dir / fn).write_text(
                f"---\n{frontmatter(meta)}\n---\n\n" + "\n\n".join(_p(body)) + "\n",
                encoding="utf-8")
        if slug not in known:
            # цикл ①②③④ у побочных арки 9 = после какой фазы читать (ТЗ, data/arcs.md)
            cyc = [CIRCLED_TO_INT[c] for p in parts for c in p.label
                   if c in CIRCLED_TO_INT]
            phase = (sorted({p.phase for p in parts if p.phase}) or [None])[0]
            phase = phase or (min(cyc) if cyc else None)
            registry.append({
                "slug": slug,
                "title": base_title,
                "title_alt": "",
                "title_orig": "",
                "type": parts[0].kind,
                "parts": len(parts),
                "read_after": {"arc": arc, "phase": phase} if phase else None,
                "source_file": parts[0].source_ref.strip(),
                "status": "pending",
            })
    idx_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────── main ───────────────────────────

def main() -> None:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help=".epub или папка с .epub")
    ap.add_argument("--arc", type=int, required=True)
    ap.add_argument("--out", type=Path, default=None, help="куда писать (без него — dry-run)")
    ap.add_argument("--volume", type=int, default=None)
    ap.add_argument("--phase", type=int, default=None, help="фаза по умолчанию для всех глав")
    ap.add_argument("--offset", type=int, default=0, help="сдвиг сквозной нумерации")
    ap.add_argument("--append", action="store_true",
                    help="дописать к существующему out (продолжить нумерацию по _manifest.json)")
    ap.add_argument("--order-from-filename", action="store_true",
                    help="для папки: порядок и номер главы из префикса имени файла")
    ap.add_argument("--pending-dir", type=Path, default=None,
                    help="куда класть побочные (по умолчанию <out>/../_pending)")
    ap.add_argument("--keep-side", action="store_true",
                    help="НЕ выносить побочные в _pending, оставить в основном контенте")
    ap.add_argument("--show-titles", action="store_true", help="печатать названия (спойлеры!)")
    args = ap.parse_args()

    sources = sorted(args.source.glob("*.epub")) if args.source.is_dir() else [args.source]
    if not sources:
        sys.exit(f"Не найдено .epub в {args.source}")

    offset = args.offset
    prev_manifest: dict = {}
    prev_chapters: list[dict] = []
    if args.append and args.out and (args.out / "_manifest.json").exists():
        prev_manifest = json.loads((args.out / "_manifest.json").read_text("utf-8"))
        prev_chapters = prev_manifest.get("chapters", [])
        nums = [int(c["number"]) for c in prev_chapters
                if (c.get("number") or "").isdigit()]
        offset = max(nums) if nums else offset
        print(f"append: на диске {len(prev_chapters)} блоков, продолжаю нумерацию с {offset + 1}")

    all_chapters: list[Chapter] = []
    all_images: dict[str, bytes] = {}
    toc_all: list[str] = []

    orphan_images: set[str] = set()
    for src in sources:
        epub = Epub(src)
        hint = filename_hint(src) if args.order_from_filename else None
        chs, imgs, skipped = build_chapters(
            epub, arc=args.arc, default_phase=args.phase, filename_hint=hint)
        for c in chs:
            c.volume = c.volume or args.volume
            c.body = trim_scene_breaks(normalize_typography(c.body))
        if hint and chs:
            chs[0].order_release = hint.get("order")
        all_chapters.extend(chs)
        every = epub.all_images()
        all_images.update(every)
        referenced = {im for c in chs for im in c.illustrations}
        orphan_images |= (set(every) - referenced)   # + картинки преамбулы/обложек
        toc_all.extend(epub.toc_labels())
        print(f"{src.name}: spine={len(epub.spine)}  блоков={len(chs)}  "
              f"картинок={len(every)} (в тексте {len(referenced)})  "
              f"преамбула пропущена={skipped}")

    if args.order_from_filename:
        order = [(c.order_release if c.order_release else 1e9, i)
                 for i, c in enumerate(all_chapters)]
        all_chapters = [all_chapters[i] for _, i in sorted(order)]

    # ── переименование иллюстраций в стабильную схему i_NNN (ТЗ §6.1) ──
    # порядок — по первому появлению в тексте, затем «сироты» для галереи тома
    img_start = 0
    if args.append and args.out and (args.out / "images").exists():
        nums = [int(m.group(1)) for f in (args.out / "images").glob("i_*")
                if (m := re.match(r"i_(\d+)", f.name))]
        img_start = max(nums) if nums else 0
    rename: dict[str, str] = {}
    ordered = [im for c in all_chapters for im in c.illustrations] + sorted(orphan_images)
    for name in dict.fromkeys(ordered):
        ext = Path(name).suffix.lower().replace(".jpeg", ".jpg") or ".jpg"
        rename[name] = f"i_{img_start + len(rename) + 1:03d}{ext}"
    all_images = {rename.get(k, k): v for k, v in all_images.items()}
    orphan_images = {rename.get(k, k) for k in orphan_images}
    for c in all_chapters:
        c.illustrations = [rename.get(x, x) for x in c.illustrations]
        for old, new in rename.items():
            c.body = c.body.replace(f"@@IMAGE:{old}@@", f"@@IMAGE:{new}@@")

    # ── карантин побочных историй (ТЗ §6.4): извлечь, описать, отложить ──
    pending = [c for c in all_chapters if c.kind in ("side", "if")]
    main_chapters = [c for c in all_chapters if c.kind not in ("side", "if")]
    quarantine = pending and not args.keep_side
    story = main_chapters if quarantine else all_chapters

    report = assign_numbers(story, offset=offset, order_offset=len(prev_chapters))

    rep = Reporter(args.show_titles)
    rep.table(story)
    rep.summary(story, report, binaries=len(all_images), inline_units=all_chapters)
    if pending:
        print(f"\nпобочных историй извлечено: {len(pending)}"
              + ("  → в _pending, в приложении не показываются" if quarantine
                 else "  (--keep-side: оставлены в основном контенте)"))
    if orphan_images:
        print(f"иллюстраций без привязки к тексту (в галерею тома): {len(orphan_images)}")

    # сверка с TOC
    if toc_all:
        toc_ch = [t for t in toc_all if classify_heading(t)]
        print(f"\nсверка с TOC: строк в оглавлении {len(toc_all)} "
              f"(из них похожи на главы {len(toc_ch)}), собрано блоков {len(all_chapters)}")
        if len(toc_ch) and abs(len(toc_ch) - len(all_chapters)) > 2:
            print("! расхождение TOC и spine — идём по spine, TOC неполный (это ожидаемо)")

    if not args.out:
        print("\n(dry-run — ничего не записано; добавь --out)")
        return

    img_dir = args.out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for name, data in all_images.items():
        (img_dir / name).write_bytes(data)

    # per-kind счётчик для slug безномерных блоков (interlude-01, prologue-02, …);
    # в режиме --append продолжаем нумерацию slug'ов с того, что уже на диске
    seen: dict[str, int] = {}
    for pc in prev_chapters:
        seen[pc["type"]] = seen.get(pc["type"], 0) + 1
    new_slugs = []
    for ch in story:
        idx = seen.get(ch.kind, 0)
        seen[ch.kind] = idx + 1
        new_slugs.append(write_chapter(args.out, ch, args.arc, index=idx))

    merged = prev_chapters + manifest_rows(story, slugs=new_slugs)
    write_manifest_rows(args.out, merged, extra={
        "arc": args.arc,
        "source": (prev_manifest.get("source", []) if isinstance(prev_manifest.get("source"), list) else [])
                  + [s.name for s in sources],
        "toc_labels": (prev_manifest.get("toc_labels", []) or []) + toc_all,
        "orphan_images": sorted(set(prev_manifest.get("orphan_images", []) or []) | orphan_images),
        "images_total": img_start + len(rename),
        "generator": "epub_to_md.py",
    })
    print(f"\nзаписано в {args.out}: +{len(story)} файлов "
          f"(всего {len(merged)}), {len(all_images)} иллюстраций")

    if quarantine:
        pdir = args.pending_dir or (args.out.parent / "_pending")
        _write_pending(pdir, args.arc, pending, all_images)
        print(f"побочные: {len(pending)} файлов в {pdir / 'side'}, реестр обновлён")


if __name__ == "__main__":
    main()
