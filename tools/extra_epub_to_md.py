#!/usr/bin/env python3
"""
extra_epub_to_md.py — конвертер сборника «Побочные истории» (epub) в
content/extra/ (раздел «Дополнительно», см. prototypes/extra-prototype.html).

Сборник устроен иначе, чем эпаб отдельной арки: важна не последовательность
(spine), а дерево toc.ncx — оно и даёт категорию, и даёт «после чего читать»:

  Арка N. <…>
    Том NN / Танпэнсю NN          — группа-контейнер, задаёт read_after
      <история>                   — один файл; номерные <h4> внутри — просто
                                     разбивка на сцены одной истории, не главы
      Ex-N «<название>»           — целое побочное издание: каждый ребёнок —
                                     часть (part 1..N) одной серии
  + 6 самостоятельных категорий в конце (Comic Alive, IF, 2× день рождения,
    ивенты, твиттер) — без read_after.

Статус перевода («нет перевода» / «неполный перевод» / «скоро») переводчики
уже пишут текстом прямо в подписи оглавления — достаём его оттуда, не гадаем.

Истории с одинаковым базовым названием, встречающиеся в разных томах одной
арки («No Stella — No Life 1..5») — после построения полного списка
схлопываются в одну серию (part 1..N), см. _group_series().

Выход:
  content/extra/<slug>[-NN].md   frontmatter: title/title_jp/category/tags/
                                  translator/fanart/status/part/parts_total/
                                  read_after_arc/read_after_container
  content/extra/images/i_NNN.ext
  content/extra/_index.json      реестр — одна запись на историю/серию
  content/extra/_foreword.md     «Предисловие» + «Виды побочных историй» —
                                  справочный текст сборника, не история

  python tools/extra_epub_to_md.py "sources/side/....epub" --out content/extra
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
    sys.exit("Нужен beautifulsoup4 + lxml:  pip install beautifulsoup4 lxml")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    SCENE_BREAK, force_utf8_stdout, is_scene_break, normalize_typography,
    trim_scene_breaks, write_text_lf,
)
from epub_to_md import Epub, _slugify_lat  # noqa: E402

NCX = "{http://www.daisy.org/z3986/2005/ncx/}"

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
         "VIII": 8, "IX": 9, "X": 10}

SPECIAL_CATEGORY = {
    "Неадаптированные истории из журнала Comic Alive": "comic_alive",
    "Альтернативные Истории": "if",
    "Спешлы ко Дню Рождения Эмилии": "birthday_emilia",
    "Спешлы ко Дню Рождения Рем и Рам": "birthday_remram",
    "Ивентовые Спешлы": "event",
    "Истории с Твиттера": "twitter",
}
SKIP_TOP = {"Предисловие", "Виды побочных историй"}

_STATUS_RE = re.compile(r"\((нет перевода|неполный перевод|скоро)\)\s*$", re.I)
_STATUS_MAP = {"нет перевода": "no_translation", "неполный перевод": "partial",
               "скоро": "soon"}
_VOL_RE = re.compile(r"^(Том|Танпэнсю)\s*(\d+)", re.I)
_EX_RE = re.compile(r"^Ex\s*(\d+)?\s*[«\"](.+?)[»\"]", re.I)


# ─────────────────────────── дерево toc.ncx ───────────────────────────

class Node:
    __slots__ = ("label", "href", "children")

    def __init__(self, label: str, href: str, children: list["Node"]):
        self.label = label
        self.href = href.split("#")[0] if href else ""
        self.children = children


def load_tree(epub: Epub) -> list[Node]:
    real = epub._resolve("toc.ncx") or next(
        (it["href"] for it in epub.manifest.values()
         if it["type"] == "application/x-dtbncx+xml"), None)
    if not real:
        sys.exit("toc.ncx не найден в epub")
    real = epub._resolve(real) or real
    root = ET.fromstring(epub.zip.read(real))

    def build(np) -> Node:
        text_el = np.find(f"{NCX}navLabel/{NCX}text")
        content_el = np.find(f"{NCX}content")
        label = (text_el.text or "").strip() if text_el is not None else ""
        href = content_el.get("src") if content_el is not None else ""
        kids = [build(k) for k in np.findall(f"{NCX}navPoint")]
        return Node(label, href, kids)

    navmap = root.find(f"{NCX}navMap")
    return [build(np) for np in navmap.findall(f"{NCX}navPoint")]


def is_leaf_story(node: Node) -> bool:
    """Лист — либо совсем без детей, либо все дети указывают на тот же файл,
    что и сам узел (внутрифайловые метки — номера сцен, «Глава Первая/Вторая»,
    имена персонажей в теме-антологии вроде «Гарем IF (Похоть)» — не отдельные
    истории, а разметка одного файла)."""
    if not node.children:
        return True
    if not node.href:
        return False
    return all(c.href == node.href for c in node.children)


# ─────────────────────────── разбор одной истории ───────────────────────────

_DIVIDER_RE = re.compile(
    r"^(?:[*※＊✽✼❋·•∙◦●○◆◇■□▲△▼▽]\s*){2,}$")  # тот же набор, что и в is_scene_break,
                                                # но с пробелами между значками —
                                                # так этот сборник и оформляет разделители


def _is_divider(text: str) -> bool:
    return is_scene_break(text) or bool(_DIVIDER_RE.match(text))


def parse_story(html: str) -> dict:
    """Возвращает title/title_jp/tags/translator/fanart/body(md)/image_srcs/sub_hrefs.

    sub_hrefs — редкий случай: страница-указатель вида «эта история — слияние
    ранее вышедших: <ol><li><a href=…>» — реальный текст лежит в файлах по
    этим ссылкам, а не в этом файле; emit_story() их подтягивает и склеивает."""
    soup = BeautifulSoup(html, "lxml")
    body_el = soup.body or soup
    blocks = [el for el in body_el.find_all(recursive=False)
              if getattr(el, "name", None) in
              ("h1", "h2", "h3", "h4", "h5", "p", "div", "blockquote", "img",
               "ol", "ul")]

    title, title_jp, translator, fanart = "", "", "", ""
    tags: list[str] = []
    md: list[str] = []
    image_srcs: list[str] = []
    sub_hrefs: list[str] = []
    internal_links: list[str] = []   # ссылки на другие файлы epub внутри обычного
                                     # текста («это обновлённая версия вышедшей …»)

    in_meta = True

    for el in blocks:
        name = el.name
        if name in ("ol", "ul"):
            links = el.find_all("a", href=True)
            items = el.find_all("li")
            real_files = [a["href"] for a in links
                         if not a["href"].startswith(("http://", "https://", "#"))
                         and re.search(r"\.x?html?(#|$)", a["href"], re.I)]
            if links and items and len(real_files) == len(links) == len(items):
                # чистый список-редирект «эта история объединяет вышедшие: …»
                sub_hrefs.extend(h.split("#")[0] for h in real_files)
            else:
                # обычный список (сноски, перечисление в тексте) — как текст
                text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
                if text:
                    in_meta = False
                    md.append(normalize_typography(text))
            continue
        if name == "img":
            # картинка — самостоятельный блочный тег в этом epub (не внутри <p>),
            # find_all("img") её не найдёт саму себя — обрабатываем явно
            src = el.get("src") or ""
            if src:
                image_srcs.append(src)
                md.append(f"@@IMAGE:{src}@@")
            in_meta = False
            continue
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()

        if name in ("h1", "h2", "h3") and not title:
            title = text
            continue
        if name in ("h4", "h5"):
            in_meta = False
            md.append(SCENE_BREAK)
            continue

        if in_meta:
            if re.match(r"^[『「].+[』」]$", text):
                title_jp = text.strip("『』「」")
                continue
            if re.match(r"^\[.*#\S+.*\]$", text):
                tags = re.findall(r"#(\S+?)(?=[ |\]])", text + " ")
                continue
            if re.match(r"^(Перевод|Редактура|Правка|Ред\.)", text, re.I):
                translator = f"{translator}; {text}" if translator else text
                continue
            if re.match(r"^Фан-арт", text, re.I):
                fanart = f"{fanart}; {text}" if fanart else text
                continue
            if not text or _is_divider(text):
                if text:
                    in_meta = False        # разделитель — конец шапки истории
                    md.append(SCENE_BREAK)
                continue
            in_meta = False                # что-то незнакомое — тело уже началось

        for img in el.find_all("img"):
            src = img.get("src") or ""
            if src:
                image_srcs.append(src)
                md.append(f"@@IMAGE:{src}@@")
        for a in el.find_all("a", href=True):
            href = a["href"]
            if (not href.startswith(("http://", "https://", "#"))
                    and re.search(r"\.x?html?(#|$)", href, re.I)):
                internal_links.append(href.split("#")[0])
        if text and not _is_divider(text):
            md.append(normalize_typography(text))
        elif _is_divider(text):
            md.append(SCENE_BREAK)

    body = trim_scene_breaks("\n\n".join(md))
    return {"title": title, "title_jp": title_jp, "tags": tags,
            "translator": translator, "fanart": fanart, "body": body,
            "image_srcs": image_srcs, "sub_hrefs": sub_hrefs,
            "internal_links": internal_links}


# ─────────────────────────── сборка реестра ───────────────────────────

class Converter:
    def __init__(self, epub: Epub):
        self.epub = epub
        self.entries: list[dict] = []   # «сырые» — до группировки по сериям
        self.seen_href: set[str] = set()
        self.img_map: dict[str, str] = {}     # исходное имя файла → i_NNN.ext
        self.img_bytes: dict[str, bytes] = {}
        self.warnings: list[str] = []

    # ── картинки ──
    def _rename_image(self, src_href: str, base_href: str) -> str | None:
        got = self.epub.image_bytes(src_href, base_href)
        if not got:
            self.warnings.append(f"картинка не найдена: {src_href} (в {base_href})")
            return None
        orig_name, data = got
        if orig_name in self.img_map:
            return self.img_map[orig_name]
        ext = Path(orig_name).suffix or ".jpg"
        new = f"i_{len(self.img_map) + 1:03d}{ext}"
        self.img_map[orig_name] = new
        self.img_bytes[new] = data
        return new

    def _read_href(self, href: str) -> str | None:
        real = self.epub._resolve(href)
        if not real:
            return None
        return self.epub.zip.read(real).decode("utf-8", "replace")

    # ── одна история ──
    def emit_story(self, node: Node, *, category: str, arc: int | None,
                   container: list[str | None], order: int):
        if not node.href:
            return
        if node.href in self.seen_href:
            self.warnings.append(f"повтор ссылки на файл, пропущено: {node.href} "
                                 f"({node.label!r})")
            return
        self.seen_href.add(node.href)

        m = _STATUS_RE.search(node.label)
        status = _STATUS_MAP[m.group(1).lower()] if m else "ok"
        toc_title = _STATUS_RE.sub("", node.label).strip()

        html = self._read_href(node.href)
        if html is None:
            self.warnings.append(f"файл не найден в epub: {node.href} ({node.label!r})")
            parsed = {"title": toc_title, "title_jp": "", "tags": [],
                      "translator": "", "fanart": "", "body": "", "image_srcs": []}
        else:
            parsed = parse_story(html)
            # заголовок оглавления — то, что реально выбрал переводчик для
            # навигации («Глава I. Начало мечты»), внутренний <h3> файла часто
            # короче и обезличенней («Глава», «Пролог») — предпочитаем toc_title
            parsed["title"] = toc_title or parsed["title"]
            # «эта история — слияние ранее вышедших: <ol><li><a href=…>» —
            # сам файл пуст, реальный текст в подшитых по ссылкам файлах
            base_dir = node.href.rsplit("/", 1)[0] if "/" in node.href else ""
            stitched_new = False
            for href in parsed["sub_hrefs"]:
                sub_href = f"{base_dir}/{href}" if base_dir else href
                if sub_href in self.seen_href:
                    continue                    # уже забран как своя toc-запись раньше
                self.seen_href.add(sub_href)
                sub_html = self._read_href(sub_href)
                if sub_html is None:
                    self.warnings.append(f"подшитый файл не найден: {sub_href} "
                                         f"(из {node.href})")
                    continue
                sub = parse_story(sub_html)
                if sub["body"]:
                    parsed["body"] = (parsed["body"] + f"\n\n{SCENE_BREAK}\n\n"
                                     + sub["body"] if parsed["body"] else sub["body"])
                    stitched_new = True
                # подшитый файл лежит в той же папке (Text/), так что его
                # относительные пути на картинки («../Images/x.jpg») уже верны
                # и относительно node.href — переписывать их не нужно
                parsed["image_srcs"] += sub["image_srcs"]
            # редирект-страница, все части которой уже забраны как отдельные
            # toc-записи раньше (более ранний релиз до объединения) — сама она
            # не несёт ничего нового, кроме мусора вида «объединение вышедших»
            if parsed["sub_hrefs"] and not stitched_new and len(parsed["body"].split()) < 80:
                return
            # «это обновлённая версия ранее вышедшей „…“» — одиночная ссылка
            # прямо в тексте (не список), а не отдельная запись в оглавлении;
            # если то, на что она указывает, уже забрано — сама пометка мусор
            if parsed["internal_links"] and len(parsed["body"].split()) < 80:
                targets = {f"{base_dir}/{h}" if base_dir else h
                          for h in parsed["internal_links"]}
                if targets and targets <= self.seen_href:
                    return

        body = parsed["body"]
        for src in parsed["image_srcs"]:
            new = self._rename_image(src, node.href)
            if new:
                body = body.replace(f"@@IMAGE:{src}@@", f"![](./images/{new})")
            else:
                body = body.replace(f"@@IMAGE:{src}@@\n\n", "").replace(f"@@IMAGE:{src}@@", "")

        node_dir = node.href.rsplit("/", 1)[0] if "/" in node.href else ""
        resolved_links = {f"{node_dir}/{h}" if node_dir else h
                          for h in parsed.get("internal_links", [])}

        self.entries.append({
            "title": parsed["title"] or toc_title,
            "title_jp": parsed["title_jp"],
            "tags": parsed["tags"],
            "translator": parsed["translator"],
            "fanart": parsed["fanart"],
            "category": category,
            "status": status,
            "arc": arc,
            "container": container[0],
            "order": order,
            "body": body,
            "words": len(body.split()),
            "source_ref": node.href,
            "internal_links": resolved_links,
        })

    # ── издание из нескольких частей: Ex-книга или тематический сборник вроде
    #    «Мимагау IF» / «Гарем IF (Похоть)» — у узла свой href (обложка/интро),
    #    а у детей — каждый в своём файле; схлопываем сразу в одну серию ──
    def emit_group(self, node: Node, *, disp_title: str, group_category: str,
                   category: str, arc: int | None, container: list[str | None],
                   order: int):
        parts_nodes = [c for c in node.children if c.href]
        if not parts_nodes:
            self.warnings.append(f"группа без частей: {node.label!r}")
            return

        # статус — по toc-пометке самого узла-группы, если она есть («Виртуозность
        # перед Театром (нет перевода)»): относится сразу ко всем частям, у них
        # самих такой пометки обычно нет
        m = _STATUS_RE.search(node.label)
        group_status = _STATUS_MAP[m.group(1).lower()] if m else None

        part_start = len(self.entries)

        # у тематических сборников (не Ex) собственный файл узла часто несёт
        # реальный текст, а не просто оглавление — как у «Аямацу IF» (86 КБ
        # прозы под обложкой с одним «Блог» в довесок). Ex не трогаем: там свой
        # файл почти всегда голый список ссылок на те же главы (Ex1.xhtml), и
        # разбирать его ещё раз означало бы дублировать/подмешать те же главы.
        if group_category != "ex" and node.href not in self.seen_href:
            html = self._read_href(node.href)
            if html:
                own = parse_story(html)
                if len(own["body"].split()) >= 15:
                    self.seen_href.add(node.href)
                    body = own["body"]
                    for src in own["image_srcs"]:
                        new = self._rename_image(src, node.href)
                        if new:
                            body = body.replace(f"@@IMAGE:{src}@@", f"![](./images/{new})")
                    self.entries.append({
                        "title": disp_title, "title_jp": own["title_jp"],
                        "tags": own["tags"], "translator": own["translator"],
                        "fanart": own["fanart"], "category": category,
                        "status": group_status or "ok", "arc": arc,
                        "container": container[0], "order": order, "body": body,
                        "words": len(body.split()), "source_ref": node.href,
                        "internal_links": set(),
                    })

        for c in parts_nodes:
            self.emit_story(c, category=category, arc=arc, container=container,
                            order=order)
        parts = self.entries[part_start:]
        if not parts:
            return
        for p in parts:
            p["series_key"] = f"{group_category}::{arc}::{disp_title}"
            p["series_title"] = disp_title
            p["category"] = group_category
            if group_status:
                p["status"] = group_status

    # ── обход дерева ──
    # container — контейнер [str|None] на всё дерево одной арки/категории: siblings
    # (Том 6, затем Ex1) должны видеть контейнер, обновлённый предыдущим соседом,
    # а не тот, что был на входе в родителя — поэтому не параметр, а общая ячейка.
    def walk(self, node: Node, *, category: str, arc: int | None,
            container: list[str | None], order: list[int]):
        # «Том NN»/«Танпэнсю NN» — это ВСЕГДА контейнер, а не история, даже
        # если у него пока нет детей (ещё не вышедший том онгоинга арки 10):
        # проверяем это раньше is_leaf_story, иначе пустой том сам становится
        # «историей» из 0 слов.
        mv = _VOL_RE.match(node.label)
        if mv:
            container[0] = node.label
            for c in node.children:
                self.walk(c, category=category, arc=arc, container=container, order=order)
            return
        if is_leaf_story(node):
            order[0] += 1
            self.emit_story(node, category=category, arc=arc, container=container,
                            order=order[0])
            return
        # не лист. Если у узла есть собственный href — это не просто папка,
        # а многочастное издание (Ex-книга или тематический сборник наподобие
        # «Мимагау IF»): дети в разных файлах, но объединены общим заголовком.
        if node.href:
            order[0] += 1
            mex = _EX_RE.match(node.label)
            if mex:
                disp_title, group_cat = mex.group(2), "ex"
            else:
                disp_title = _STATUS_RE.sub("", node.label).strip()
                group_cat = category
            self.emit_group(node, disp_title=disp_title, group_category=group_cat,
                            category=category, arc=arc, container=container,
                            order=order[0])
            return
        # чистая папка без своего файла — просто спускаемся ниже
        for c in node.children:
            self.walk(c, category=category, arc=arc, container=container, order=order)

    def run(self, tree: list[Node]) -> str:
        foreword_parts = []
        for top in tree:
            if top.label in SKIP_TOP:
                html = self._read_href(top.href) if top.href else None
                if html:
                    p = parse_story(html)
                    foreword_parts.append(f"## {top.label}\n\n" +
                                          "\n\n".join(p["body"].split("\n\n")))
                continue
            m_arc = re.match(r"^Арка\s+([IVX]+)\.", top.label)
            if m_arc:
                arc = ROMAN.get(m_arc.group(1))
                box, ordr = [None], [0]
                for c in top.children:      # не сам узел арки — у него тоже есть
                    self.walk(c, category="side", arc=arc, container=box, order=ordr)
                continue
            category = SPECIAL_CATEGORY.get(top.label, _slugify_lat(top.label))
            box, ordr = [None], [0]
            for c in top.children:          # href, иначе арка сама станет «историей»
                self.walk(c, category=category, arc=None, container=box, order=ordr)
        return "\n\n".join(foreword_parts)


# ─────────────────────────── группировка серий ───────────────────────────

_SERIES_TAIL = re.compile(
    r"\s*(?:[—\-]\s*)?(?:№\s*)?\d+$|"
    r"\s*\|\s*(Экстра|После|Продолжение|Вступительная часть|Часть инцидента)\s*$",
    re.I,
)


def _series_base(title: str) -> str:
    prev = None
    t = title
    while prev != t:
        prev = t
        t = _SERIES_TAIL.sub("", t).strip()
    return t.lower()


def group_series(entries: list[dict]) -> list[dict]:
    """Истории с общим базовым названием в одной арке/категории → одна серия
    (part 1..N по порядку появления). Ex уже сгруппирован при обходе."""
    buckets: dict[tuple, list[dict]] = {}
    for e in entries:
        if "series_key" in e:      # Ex — уже своя серия
            continue
        base = _series_base(e["title"])
        key = (e["category"], e["arc"], base)
        buckets.setdefault(key, []).append(e)

    for (category, arc, base), group in buckets.items():
        if len(group) < 2 or not base:
            continue
        group.sort(key=lambda e: (e["arc"] or 0, e["order"]))
        # название серии — оригинальное название первой по порядку части
        # (не base.title() — он ломает регистр русских предлогов/союзов)
        series_title = group[0]["title"]
        for e in group:
            e["series_key"] = f"{category}::{arc}::{base}"
            e["series_title"] = series_title

    return entries


def drop_dead_stubs(items: list[dict], seen_href: set[str]) -> tuple[list[dict], int]:
    """Серии/одиночки, где КАЖДАЯ часть — короткая пометка «устаревшая версия,
    смотрите такой-то файл» и все такие ссылки уже забраны как свои записи —
    целиком мусор: реальный текст лежит в другой, полной записи реестра.
    Проверяем уже после полного обхода — только тогда seen_href содержит и
    более поздние (по дереву) файлы, на которые могла ссылаться более ранняя
    забытая версия."""
    out, dropped = [], 0
    for item in items:
        parts = item["parts"]
        if all(p.get("internal_links") and p["internal_links"] <= seen_href
              and len(p["body"].split()) < 80 for p in parts):
            dropped += 1
            continue
        out.append(item)
    return out, dropped


def build_series(entries: list[dict]) -> list[dict]:
    """Схлопывает сырые записи в финальные серии/одиночные истории для записи."""
    groups: dict[str, list[dict]] = {}
    singles: list[dict] = []
    for e in entries:
        k = e.get("series_key")
        if k:
            groups.setdefault(k, []).append(e)
        else:
            singles.append(e)

    out: list[dict] = []
    for k, parts in groups.items():
        if k.startswith("ex::"):
            parts.sort(key=lambda e: e["order"])
        else:
            parts.sort(key=lambda e: (e["arc"] or 0, e["order"]))
        out.append({"kind": "series", "title": parts[0].get("series_title") or parts[0]["title"],
                    "parts": parts})
    for e in singles:
        out.append({"kind": "single", "title": e["title"], "parts": [e]})
    return out


# ─────────────────────────── запись ───────────────────────────

_FM_ORDER = ["title", "title_jp", "category", "status", "part", "parts_total",
             "series_title", "read_after_arc", "read_after_container", "tags",
             "translator", "fanart", "source_ref"]


def _fm(meta: dict) -> str:
    lines = []
    for k in _FM_ORDER:
        v = meta.get(k)
        if v in (None, "", []):
            continue
        if isinstance(v, (str, list)):
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def write_all(items: list[dict], out: Path, conv: Converter, foreword: str) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    img_dir = out / "images"
    if conv.img_bytes:
        img_dir.mkdir(exist_ok=True)
        for name, data in conv.img_bytes.items():
            (img_dir / name).write_bytes(data)

    used_slugs: set[str] = set()
    registry: list[dict] = []

    for item in items:
        base_slug = _slugify_lat(item["title"])[:60] or "story"
        slug = base_slug
        i = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{i}"
            i += 1
        used_slugs.add(slug)

        parts = item["parts"]
        n = len(parts)
        part_slugs = []
        for i, p in enumerate(parts, 1):
            fn = f"{slug}-{i:02d}.md" if n > 1 else f"{slug}.md"
            meta = {
                "title": p["title"], "title_jp": p["title_jp"],
                "category": p["category"], "status": p["status"],
                "part": i if n > 1 else None, "parts_total": n if n > 1 else None,
                "series_title": item["title"] if n > 1 else None,
                "read_after_arc": p["arc"], "read_after_container": p["container"],
                "tags": p["tags"], "translator": p["translator"], "fanart": p["fanart"],
                "source_ref": p["source_ref"],
            }
            body = p["body"] or "*(перевод пока отсутствует)*"
            write_text_lf(out / fn, f"---\n{_fm(meta)}\n---\n\n{body}\n")
            part_slugs.append(fn[:-3])

        arc0 = parts[0]["arc"]
        cont0 = parts[0]["container"]
        registry.append({
            "slug": slug,
            "title": item["title"],
            "title_jp": parts[0]["title_jp"],
            "category": parts[0]["category"],
            "tags": parts[0]["tags"],
            "translator": parts[0]["translator"],
            "fanart": parts[0]["fanart"],
            "parts": n,
            "part_slugs": part_slugs,
            "read_after": {"arc": arc0, "container": cont0} if arc0 else None,
            "status": ("ok" if any(p["status"] == "ok" for p in parts)
                      else parts[0]["status"]),
            "words": sum(p["words"] for p in parts),
        })

    write_text_lf(out / "_index.json", json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    if foreword.strip():
        write_text_lf(out / "_foreword.md", foreword.strip() + "\n")
    return registry


# ─────────────────────────── main ───────────────────────────

def main() -> None:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub", type=Path)
    ap.add_argument("--out", type=Path, default=Path("content/extra"))
    args = ap.parse_args()

    epub = Epub(args.epub)
    tree = load_tree(epub)

    conv = Converter(epub)
    foreword = conv.run(tree)

    entries = group_series(conv.entries)
    items = build_series(entries)
    items, dropped = drop_dead_stubs(items, conv.seen_href)
    registry = write_all(items, args.out, conv, foreword)

    by_cat: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in registry:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    print(f"историй/серий: {len(registry)}  (сырых записей: {len(conv.entries)}, "
         f"отброшено мёртвых устаревших ссылок: {dropped})")
    print(f"частей суммарно: {sum(r['parts'] for r in registry)}")
    print(f"картинок: {len(conv.img_bytes)}")
    print("\nпо категориям:")
    for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {k:16} {v}")
    print("\nпо статусу:")
    for k, v in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"  {k:16} {v}")
    if conv.warnings:
        print(f"\nпредупреждений: {len(conv.warnings)}")
        for w in conv.warnings[:25]:
            print(f"  ! {w}")
        if len(conv.warnings) > 25:
            print(f"  … и ещё {len(conv.warnings) - 25}")


if __name__ == "__main__":
    main()
