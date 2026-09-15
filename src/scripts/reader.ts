import { THEMES, PAIR, DEFAULT_THEME } from "../lib/themes";
import { FONT_GROUPS, DEFAULT_FONT } from "../lib/fonts";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    __READER__: {
      arc: string;
      arcSlug: string;
      whereLabel: string;
      chId: string;
      seriesSlug: string;
      chTitle: string;
      pos: number;
      total: number;
      toc: { id: string; type: string; n: string; label: string; title: string }[];
    };
  }
}
const R = window.__READER__;
const root = document.documentElement;
root.setAttribute("data-reader", "");
const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;

/* ─────────── состояние ─────────── */
const DEF = {
  font: DEFAULT_FONT, fsa: "none",
  fs: 19, mw: 720, lh: 1.75, align: "left", indent: "0em",
  anim: "on", spoil: "on",
};
type Settings = typeof DEF;
const SKEY = "reader:set";
const S: Settings = { ...DEF, ...safe(() => JSON.parse(localStorage.getItem(SKEY) || "{}")) };
const save = () => safe(() => localStorage.setItem(SKEY, JSON.stringify(S)));

let notes: any[] = safe(() => JSON.parse(localStorage.getItem("reader:notes") || "[]")) || [];
const saveNotes = () => safe(() => localStorage.setItem("reader:notes", JSON.stringify(notes)));

// сайт-тема (палитра): общий с theme.ts ключ
type Site = { theme: string; auto: "on" | "off"; mode: "" | "dark" | "light" };
const site: Site = { theme: DEFAULT_THEME, auto: "on", mode: "", ...safe(() => JSON.parse(localStorage.getItem("rz:site") || "{}")) };
const saveSite = () => safe(() => localStorage.setItem("rz:site", JSON.stringify(site)));

function safe<T>(fn: () => T): T | undefined {
  try {
    return fn();
  } catch {
    return undefined;
  }
}

/* ─────────── трансформация текста главы ─────────── */
const text = $("#text");
[...text.querySelectorAll("p")].forEach((p, i) => {
  // абзацы внутри списка сносок — не часть основного текста: без кнопки
  // «¶» на них (иначе она же протекает в попап пояснения при клике на цифру)
  if (p.closest("[data-footnotes]")) return;
  const img = p.querySelector("img");
  if (img && p.textContent!.trim() === "") {
    const fig = document.createElement("figure");
    fig.dataset.blur = S.spoil === "on" ? "on" : "off";
    img.removeAttribute("style");
    fig.appendChild(img);
    const hide = document.createElement("button");
    hide.className = "fighide";
    hide.type = "button";
    hide.title = "Скрыть иллюстрацию";
    hide.setAttribute("aria-label", "Скрыть иллюстрацию");
    hide.innerHTML =
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l18 18"/><path d="M10.6 5.1A9 9 0 0 1 12 5c5 0 9 5 9 7a12 12 0 0 1-2.16 3M6.2 6.2A12 12 0 0 0 3 12c0 2 4 7 9 7a9 9 0 0 0 4-1"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
    fig.appendChild(hide);
    const cap = document.createElement("figcaption");
    cap.className = "cap";
    cap.textContent = "иллюстрация";
    fig.appendChild(cap);
    p.replaceWith(fig);
    return;
  }
  if (p.closest("blockquote")) return;
  p.classList.add("par");
  p.id ||= "p" + (i + 1);
  const b = document.createElement("button");
  b.className = "anchor";
  b.type = "button";
  b.dataset.id = p.id;
  b.title = "Ссылка на абзац";
  b.textContent = "¶";
  p.prepend(b);
});

/* ─────────── применение настроек ─────────── */
function applyTheme() {
  let id = site.auto === "on" ? R.arcSlug && arcThemeKey() : site.theme;
  if (!id || !THEMES[id]) id = site.auto === "on" ? arcThemeKey() : DEFAULT_THEME;
  if (!THEMES[id]) id = DEFAULT_THEME;
  if (site.mode && THEMES[id].m !== site.mode && PAIR[id]) id = PAIR[id];
  const t = THEMES[id];
  const r = root.style;
  r.setProperty("--paper", t.p);
  r.setProperty("--paper-2", t.p2);
  r.setProperty("--ink", t.i);
  r.setProperty("--ink-dim", t.d);
  r.setProperty("--c", t.g);
  r.setProperty("--gold", t.g);
  r.setProperty("--gold-soft", t.gs);
  r.setProperty("--rule", t.g + "4a");
  root.dataset.mode = t.m;
  document.querySelectorAll<HTMLElement>(".sw").forEach((x) =>
    x.setAttribute("aria-pressed", String(x.dataset.t === id)),
  );
  document.querySelectorAll<HTMLElement>("#mode .chip").forEach((c) =>
    c.setAttribute("aria-pressed", String(c.dataset.v === t.m)),
  );
  document.querySelectorAll<HTMLElement>("#autoTheme .chip").forEach((c) =>
    c.setAttribute("aria-pressed", String(c.dataset.v === site.auto)),
  );
}
function arcThemeKey(): string {
  return root.dataset.arcTheme || DEFAULT_THEME;
}

function apply() {
  const r = root.style;
  r.setProperty("--font", S.font);
  r.setProperty("--fs", S.fs + "px");
  r.setProperty("--measure", S.mw + "px");
  r.setProperty("--lh", String(S.lh));
  r.setProperty("--align", S.align);
  r.setProperty("--indent", S.indent);
  r.setProperty("--fsa", S.fsa || "none");
  root.dataset.anim = S.anim;
  ($("#fs") as HTMLInputElement).value = String(S.fs);
  $("#fsv").textContent = S.fs + "px";
  ($("#mw") as HTMLInputElement).value = String(S.mw);
  $("#mwv").textContent = S.mw + "px";
  ($("#lh") as HTMLInputElement).value = String(S.lh);
  $("#lhv").textContent = String(S.lh);
  document.querySelectorAll<HTMLElement>("figure").forEach((f) => {
    f.dataset.blur = S.spoil === "on" && !revealed.has(figKey(f)) ? "on" : "off";
  });
  document.querySelectorAll<HTMLElement>(".fontrow").forEach((c) =>
    c.setAttribute("aria-pressed", String(S[c.dataset.key as keyof Settings] === c.dataset.v)),
  );
  document.querySelectorAll<HTMLElement>(".panel .chip[data-k]").forEach((c) =>
    c.setAttribute("aria-pressed", String(S[c.dataset.k as keyof Settings] === c.dataset.v)),
  );
  applyTheme();
}

/* ─────────── чипы ─────────── */
function chips(hostId: string, key: string, items: [string, string][]) {
  const host = $("#" + hostId);
  host.innerHTML = items
    .map(([l, v]) => `<button class="chip" data-k="${key}" data-v="${v}">${l}</button>`)
    .join("");
  host.addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>(".chip");
    if (!b) return;
    (S as any)[key] = b.dataset.v;
    save();
    apply();
  });
}
chips("fsa", "fsa", [["Включено", "0.5"], ["Выключено", "none"]]);
chips("align", "align", [["Слева", "left"], ["По ширине", "justify"]]);
chips("indent", "indent", [["Нет", "0em"], ["1.2 em", "1.2em"]]);
chips("anim", "anim", [["Включено", "on"], ["Выключено", "off"]]);
chips("spoil", "spoil", [["Скрывать", "on"], ["Показывать", "off"]]);
["fs", "mw", "lh"].forEach((k) => {
  ($("#" + k) as HTMLInputElement).addEventListener("input", (e) => {
    const v = (e.target as HTMLInputElement).value;
    (S as any)[k] = k === "lh" ? parseFloat(v) : parseInt(v);
    save();
    apply();
  });
});
$("#reset").addEventListener("click", () => {
  Object.assign(S, DEF);
  save();
  apply();
  toast("Настройки сброшены");
});
/* ─────────── список шрифтов + проверка кириллицы ─────────── */
function renderFonts(hostId: string, key: string) {
  const host = $("#" + hostId);
  host.innerHTML = FONT_GROUPS.map(
    ([group, items]) =>
      `<div class="fgroup">${group}</div>` +
      items
        .map(
          ([label, stack]) =>
            `<button class="fontrow" data-key="${key}" data-v="${stack}" data-stack="${stack}" style="font-family:${stack}">${label}</button>`,
        )
        .join(""),
  ).join("");
  host.addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>(".fontrow");
    if (!b) return;
    (S as any)[key] = b.dataset.v;
    save();
    apply();
  });
}
renderFonts("fonts", "font");

const PROBE = "Дорога уходила вверх по склону";
const LAT = "The quick brown fox jumps";
function measure(txt: string, family: string) {
  const c = (measure as any)._c || ((measure as any)._c = document.createElement("canvas").getContext("2d"));
  c.font = `36px ${family}`;
  return c.measureText(txt).width;
}
function auditFonts() {
  const refCyr = measure(PROBE, "monospace");
  const refLat = measure(LAT, "monospace");
  let broken = 0;
  let noCyr = 0;
  document.querySelectorAll<HTMLElement>(".fontrow").forEach((btn) => {
    const stack = btn.dataset.stack || "";
    const fam = stack.split(",")[0].trim();
    if (!fam.startsWith("'")) return;
    const latLoaded = Math.abs(measure(LAT, `${fam},monospace`) - refLat) > 0.5;
    const cyrLoaded = Math.abs(measure(PROBE, `${fam},monospace`) - refCyr) > 0.5;
    if (!latLoaded) {
      btn.classList.add("bad");
      btn.title = "шрифт не загрузился";
      broken++;
    } else if (!cyrLoaded) {
      btn.classList.add("bad");
      btn.title = "нет кириллицы — русский текст покажется запасным шрифтом";
      noCyr++;
    }
  });
  const m: string[] = [];
  if (broken) m.push(`${broken} не загрузились`);
  if (noCyr) m.push(`${noCyr} без кириллицы`);
  $("#fontnote").innerHTML = m.length ? `<p class="hint">Зачёркнуты: ${m.join(", ")}.</p>` : "";
}
(document as any).fonts?.ready.then(() => setTimeout(auditFonts, 500));

/* ─────────── палитра ─────────── */
function swatches(hostId: string, mode: "dark" | "light") {
  const host = $("#" + hostId);
  host.innerHTML = Object.entries(THEMES)
    .filter(([, t]) => t.m === mode)
    .map(
      ([id, t]) =>
        `<button class="sw" data-t="${id}"><i style="background:${t.p}"><span style="background:${t.g}"></span></i>${t.n}</button>`,
    )
    .join("");
  host.addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>(".sw");
    if (!b) return;
    site.theme = b.dataset.t!;
    site.auto = "off";
    site.mode = "";
    saveSite();
    applyTheme();
  });
}
swatches("swDark", "dark");
swatches("swLight", "light");
$("#mode").addEventListener("click", (e) => {
  const b = (e.target as HTMLElement).closest<HTMLElement>(".chip");
  if (!b) return;
  site.mode = b.dataset.v as Site["mode"];
  saveSite();
  applyTheme();
});
$("#autoTheme").addEventListener("click", (e) => {
  const b = (e.target as HTMLElement).closest<HTMLElement>(".chip");
  if (!b) return;
  site.auto = b.dataset.v as Site["auto"];
  saveSite();
  applyTheme();
});

/* ─────────── оглавление ─────────── */
// у одиночных (без серии) побочных историй кнопки/панели оглавления в DOM
// вообще нет — переходить некуда, см. read/[...id].astro (total > 1)
function buildToc() {
  const list = document.getElementById("tocList");
  if (!list) return;
  const kl: Record<string, string> = {
    prologue: "Пролог", epilogue: "Финал", interlude: "Интерлюдия",
    side: "Побочная", if: "IF", extra: "Бонус",
  };
  list.innerHTML = R.toc
    .map((c) => {
      const num = c.type === "chapter" ? String(c.n).padStart(2, "0") : "—";
      const t = c.title || c.label || kl[c.type] || c.type;
      return `<a class="tocitem ${c.id === R.chId ? "here" : ""}" href="/read/${c.id}"><span class="n">${num}</span><span>${t}</span></a>`;
    })
    .join("");
}
buildToc();
document.getElementById("tocMarkAllRead")?.addEventListener("click", () => {
  if (!confirm(`Отметить все ${R.toc.length} глав(ы)/част(и) прочитанными?`)) return;
  safe(() => {
    const p: Record<string, number> = JSON.parse(localStorage.getItem("rz:progress") || "{}");
    R.toc.forEach((c) => (p[c.id] = 1));
    localStorage.setItem("rz:progress", JSON.stringify(p));
  });
  location.reload();
});

/* ─────────── панели ─────────── */
const panels: Record<string, HTMLElement | null> = {
  gearBtn: document.getElementById("settings"),
  tocBtn: document.getElementById("tocPanel"),
  notesBtn: document.getElementById("notesPanel"),
  paletteBtn2: document.getElementById("palettePanel"),
};
Object.entries(panels).forEach(([btn, p]) => {
  if (!p) return;
  document.getElementById(btn)?.addEventListener("click", (e) => {
    e.stopPropagation();
    Object.values(panels).forEach((x) => x && x !== p && x.classList.remove("open"));
    p.classList.toggle("open");
    if (p === panels.notesBtn) renderNotes();
  });
});
document.addEventListener("click", (e) => {
  if ((e.target as HTMLElement).closest(".panel, .fab")) return;
  Object.values(panels).forEach((p) => p?.classList.remove("open"));
});

/* ─────────── прогресс + позиция ─────────── */
const bar = $("#bar");
const hpct = $("#hpct");
const PKEY = "reader:pos:" + location.pathname;
// читаем сохранённую позицию ДО первого вызова progress() ниже — иначе он
// тут же перезаписывает PKEY текущим (нулевым при загрузке) скроллом, и
// восстановление позиции внизу файла никогда не срабатывает
const savedPos: { y: number; pct: number } | undefined = safe(() =>
  JSON.parse(localStorage.getItem(PKEY) || "null"),
);
function progress() {
  const h = root;
  const pct = Math.min(100, Math.round((h.scrollTop / (h.scrollHeight - h.clientHeight)) * 100)) || 0;
  bar.style.width = pct + "%";
  hpct.textContent = pct + "%";
  safe(() => {
    localStorage.setItem(PKEY, JSON.stringify({ y: h.scrollTop, pct }));
    const prog = JSON.parse(localStorage.getItem("rz:progress") || "{}");
    // не откатываем назад: если пролистали обратно перечитать что-то, статус
    // «прочитано» и общий процент не должны слетать
    prog[R.chId] = Math.max(prog[R.chId] ?? 0, pct / 100);
    localStorage.setItem("rz:progress", JSON.stringify(prog));
    // «продолжить» на главной считается заново из rz:progress при каждом
    // визите (см. index.astro) — отдельное «последнее посещённое» не нужно.
    // Для «Дополнительного» — отдельно помечаем серию как «трогали только что»
    // (для сортировки чипов «продолжить») и снимаем ручной дисмисс чипа, раз
    // читатель сам вернулся к этой истории.
    if (R.seriesSlug) {
      const touched = JSON.parse(localStorage.getItem("rz:extra:touched") || "{}");
      touched[R.seriesSlug] = Date.now();
      localStorage.setItem("rz:extra:touched", JSON.stringify(touched));
      const dismissed = JSON.parse(localStorage.getItem("rz:extra:dismissed") || "{}");
      if (dismissed[R.seriesSlug]) {
        delete dismissed[R.seriesSlug];
        localStorage.setItem("rz:extra:dismissed", JSON.stringify(dismissed));
      }
    }
  });
}
addEventListener("scroll", progress, { passive: true });

/* появление абзацев */
const io = new IntersectionObserver(
  (es) => es.forEach((e) => e.isIntersecting && e.target.classList.add("seen")),
  { threshold: 0.08 },
);
text.querySelectorAll("p.par").forEach((p) => io.observe(p));

/* ─────────── иллюстрации: блюр / лайтбокс ─────────── */
const revealed = new Set<string>(safe(() => JSON.parse(localStorage.getItem("reader:illos:" + location.pathname) || "[]")) || []);
const figKey = (f: HTMLElement) => (f.querySelector("img")?.getAttribute("src") || "").replace(/.*\//, "");
const lb = $("#lightbox");
text.addEventListener("click", (e) => {
  const a = (e.target as HTMLElement).closest<HTMLElement>(".anchor");
  if (a) {
    const url = location.href.split("#")[0] + "#" + a.dataset.id;
    navigator.clipboard?.writeText(url);
    toast("Ссылка на абзац скопирована");
    return;
  }
  const persistRevealed = () =>
    safe(() => localStorage.setItem("reader:illos:" + location.pathname, JSON.stringify([...revealed])));
  const hb = (e.target as HTMLElement).closest<HTMLElement>(".fighide");
  if (hb) {
    e.preventDefault();
    e.stopPropagation();
    const fig = hb.closest<HTMLElement>("figure")!;
    fig.dataset.blur = "on";
    revealed.delete(figKey(fig));
    persistRevealed();
    return;
  }
  const f = (e.target as HTMLElement).closest<HTMLElement>("figure");
  if (f) {
    if (f.dataset.blur === "on") {
      f.dataset.blur = "off";
      revealed.add(figKey(f));
      persistRevealed();
    } else {
      const im = f.querySelector("img") as HTMLImageElement;
      (lb.querySelector("img") as HTMLImageElement).src = im.currentSrc || im.src;
      lb.classList.add("open");
    }
  }
});
lb.addEventListener("click", () => lb.classList.remove("open"));
addEventListener("hashchange", () => {
  const el = document.querySelector(location.hash || "#none");
  if (!el) return;
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1800);
});

/* ─────────── выделения и заметки ─────────── */
const selbar = $("#selbar");
document.addEventListener("mouseup", () => {
  const sel = getSelection();
  const txt = sel?.toString().trim() || "";
  if (!txt || txt.length < 3 || !sel!.anchorNode || !text.contains(sel!.anchorNode)) {
    selbar.style.display = "none";
    return;
  }
  const r = sel!.getRangeAt(0).getBoundingClientRect();
  selbar.style.display = "flex";
  selbar.style.top = r.top + scrollY - 46 + "px";
  selbar.style.left = Math.max(8, r.left + r.width / 2 - 90) + "px";
});
selbar.addEventListener("click", (e) => {
  const act = (e.target as HTMLElement).dataset.act;
  if (!act) return;
  const sel = getSelection()!;
  const txt = sel.toString().trim();
  const par = (sel.anchorNode?.parentElement as HTMLElement)?.closest("p.par") as HTMLElement | null;
  if (act === "copy") {
    navigator.clipboard?.writeText(txt);
    toast("Скопировано");
  } else {
    const comment = act === "note" ? prompt("Заметка к фрагменту:") || "" : "";
    notes.push({
      text: txt, comment, chapter: R.chTitle, arc: R.arc,
      anchor: par?.id || "", href: location.pathname, date: new Date().toISOString(),
    });
    saveNotes();
    if (par) par.innerHTML = par.innerHTML.replace(txt, `<mark class="note">${txt}</mark>`);
    toast(act === "note" ? "Заметка сохранена" : "Выделено");
  }
  selbar.style.display = "none";
  sel.removeAllRanges();
});
function renderNotes() {
  const list = $("#noteList");
  list.innerHTML = notes.length
    ? notes
        .map(
          (n, i) =>
            `<div class="note-row"><q>${esc(n.text)}</q>${n.comment ? `<div class="c">${esc(n.comment)}</div>` : ""}<div class="meta"><span>${esc(n.chapter || "")}${n.anchor ? " · " + n.anchor : ""}</span><button data-del="${i}">удалить</button></div></div>`,
        )
        .join("")
    : '<p class="empty">Выделите фрагмент в тексте, чтобы сохранить его сюда.</p>';
  list.onclick = (e) => {
    const d = (e.target as HTMLElement).dataset.del;
    if (d !== undefined) {
      notes.splice(+d, 1);
      saveNotes();
      renderNotes();
    }
  };
}
const esc = (s: string) => s.replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]!));
function dl(name: string, content: string, type: string) {
  const b = new Blob([content], { type });
  const u = URL.createObjectURL(b);
  const a = document.createElement("a");
  a.href = u;
  a.download = name;
  a.click();
  URL.revokeObjectURL(u);
}
$("#expMd").addEventListener("click", () =>
  dl(
    "rezero-notes.md",
    notes
      .map((n) => `> ${n.text}\n\n${n.comment || ""}\n\n— ${n.chapter}${n.anchor ? " · " + n.anchor : ""}\n\n---\n`)
      .join("\n"),
    "text/markdown",
  ),
);
$("#expJson").addEventListener("click", () =>
  dl(
    "rezero-backup.json",
    JSON.stringify({ settings: S, site, notes, progress: safe(() => JSON.parse(localStorage.getItem("rz:progress") || "{}")) }, null, 2),
    "application/json",
  ),
);
$("#impJson").addEventListener("click", () => {
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".json";
  inp.onchange = () => {
    const f = inp.files![0];
    const rd = new FileReader();
    rd.onload = () => {
      try {
        const dobj = JSON.parse(rd.result as string);
        Object.assign(S, dobj.settings || {});
        Object.assign(site, dobj.site || {});
        notes = dobj.notes || [];
        if (dobj.progress) safe(() => localStorage.setItem("rz:progress", JSON.stringify(dobj.progress)));
        save();
        saveNotes();
        saveSite();
        apply();
        renderNotes();
        toast("Данные загружены");
      } catch {
        toast("Не удалось прочитать файл");
      }
    };
    rd.readAsText(f);
  };
  inp.click();
});

/* ─────────── мелочи ─────────── */
let toastTimer: any;
function toast(m: string) {
  const t = $("#toast");
  t.textContent = m;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 1900);
}
addEventListener("keydown", (e) => {
  if ((e.target as HTMLElement).tagName === "INPUT" || (e.target as HTMLElement).tagName === "TEXTAREA") return;
  const k = e.key.toLowerCase();
  if (k === "s") $("#gearBtn").click();
  else if (k === "c") document.getElementById("tocBtn")?.click();
  else if (k === "n") $("#notesBtn").click();
  else if (k === "t") $("#paletteBtn2").click();
  else if (e.key === "+" || e.key === "=") { S.fs = Math.min(30, S.fs + 1); save(); apply(); }
  else if (e.key === "-") { S.fs = Math.max(15, S.fs - 1); save(); apply(); }
  else if (e.key === "ArrowLeft") $<HTMLAnchorElement>(".pager a:first-child")?.click?.();
  else if (e.key === "ArrowRight") $<HTMLAnchorElement>(".pager a:last-child")?.click?.();
});

apply();
progress();
if (savedPos && savedPos.y > 400) {
  setTimeout(() => {
    scrollTo(0, savedPos.y);
    toast("Вы остановились на " + savedPos.pct + "%");
  }, 400);
}

/* ─────────── пояснения — попап вместо перехода в конец главы ───────────
   работает с любыми главами, где сноски оформлены как обычный markdown-
   footnote ([^N] / [^N]: текст) — Astro сам собирает их в <sup><a
   data-footnote-ref> и <section data-footnotes>, список внизу мы прячем
   в CSS и просто переиспользуем его содержимое здесь. */
(function setupFootnotePopups() {
  const text = document.getElementById("text");
  const refs = text ? [...text.querySelectorAll<HTMLAnchorElement>("a[data-footnote-ref]")] : [];
  if (!refs.length) return;

  const pop = document.createElement("div");
  pop.className = "fnpop";
  pop.hidden = true;
  document.body.appendChild(pop);
  let openRef: HTMLAnchorElement | null = null;

  function close() {
    if (!openRef) return;
    pop.hidden = true;
    openRef.setAttribute("aria-expanded", "false");
    openRef = null;
  }

  function place(ref: HTMLAnchorElement) {
    const r = ref.getBoundingClientRect();
    pop.hidden = false;
    const pr = pop.getBoundingClientRect();
    let left = r.left + r.width / 2 - pr.width / 2;
    left = Math.max(16, Math.min(left, innerWidth - pr.width - 16));
    let top = r.bottom + 10;
    let below = true;
    if (top + pr.height > innerHeight - 16 && r.top - pr.height - 10 > 0) {
      top = r.top - pr.height - 10;
      below = false;
    }
    pop.style.left = left + "px";
    pop.style.top = top + scrollY + "px";
    pop.style.setProperty("--fnpop-arrow", r.left + r.width / 2 - left + "px");
    pop.classList.toggle("up", !below);
  }

  refs.forEach((ref) => {
    ref.setAttribute("aria-expanded", "false");
    ref.addEventListener("click", (e) => {
      e.preventDefault();
      if (openRef === ref) {
        close();
        return;
      }
      const id = ref.getAttribute("href")?.slice(1);
      const li = id ? document.getElementById(id) : null;
      if (!li) return;
      const clone = li.cloneNode(true) as HTMLElement;
      // это класс, а не data-атрибут — remark-gfm рендерит его как
      // class="data-footnote-backref", без такого селектора «↩» оставалась
      // в попапе как есть, без шрифта из настроек (см. историю правок)
      clone.querySelectorAll("a.data-footnote-backref").forEach((a) => a.remove());
      pop.innerHTML = "";
      pop.append(...Array.from(clone.childNodes));
      openRef?.setAttribute("aria-expanded", "false");
      openRef = ref;
      ref.setAttribute("aria-expanded", "true");
      place(ref);
    });
  });

  document.addEventListener("click", (e) => {
    if (!openRef) return;
    const t = e.target as Node;
    if (pop.contains(t) || openRef.contains(t)) return;
    close();
  });
  addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });
  addEventListener("scroll", close, { passive: true });
  addEventListener("resize", close);
})();
