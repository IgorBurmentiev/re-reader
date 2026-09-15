import { THEMES, PAIR, DEFAULT_THEME } from "../lib/themes";

type Site = { theme: string; auto: "on" | "off"; mode: "" | "dark" | "light" };
const KEY = "rz:site";
const root = document.documentElement;

const load = (): Site => {
  try {
    return { theme: DEFAULT_THEME, auto: "on", mode: "", ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return { theme: DEFAULT_THEME, auto: "on", mode: "" };
  }
};
const save = (s: Site) => {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {}
};

const S = load();
// тема этой страницы: у арки/главы своя (data-arc-theme), иначе — выбор пользователя
const arcTheme = root.dataset.arcTheme || "";

function effectiveId(): string {
  let id = S.auto === "on" && arcTheme ? arcTheme : S.theme;
  if (!THEMES[id]) id = DEFAULT_THEME;
  // ручной day/night перекидывает на парную тему того же оттенка
  if (S.mode && THEMES[id].m !== S.mode && PAIR[id]) id = PAIR[id];
  return id;
}

export function applyTheme() {
  const id = effectiveId();
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
  root.dataset.theme = id;
  document.querySelectorAll<HTMLElement>(".sw").forEach((x) =>
    x.setAttribute("aria-pressed", String(x.dataset.t === id)),
  );
  document.querySelectorAll<HTMLElement>("#mode .chip").forEach((c) =>
    c.setAttribute("aria-pressed", String(c.dataset.v === t.m)),
  );
  document.querySelectorAll<HTMLElement>("#autoTheme .chip").forEach((c) =>
    c.setAttribute("aria-pressed", String(c.dataset.v === S.auto)),
  );
}

// ── палитра (FAB + панель) ──
function wirePalette() {
  const fab = document.getElementById("paletteBtn");
  const panel = document.getElementById("palettePanel");
  if (!fab || !panel) return;

  const swHTML = (mode: "dark" | "light") =>
    Object.entries(THEMES)
      .filter(([, t]) => t.m === mode)
      .map(
        ([id, t]) =>
          `<button class="sw" data-t="${id}"><i style="background:${t.p}"><span style="background:${t.g}"></span></i>${t.n}</button>`,
      )
      .join("");
  const dk = panel.querySelector("#swDark");
  const lt = panel.querySelector("#swLight");
  if (dk) dk.innerHTML = swHTML("dark");
  if (lt) lt.innerHTML = swHTML("light");

  panel.querySelectorAll<HTMLElement>(".sw").forEach((b) =>
    b.addEventListener("click", () => {
      S.theme = b.dataset.t!;
      S.auto = "off";
      S.mode = "";
      save(S);
      applyTheme();
    }),
  );
  panel.querySelectorAll<HTMLElement>("#mode .chip").forEach((b) =>
    b.addEventListener("click", () => {
      S.mode = b.dataset.v as Site["mode"];
      save(S);
      applyTheme();
    }),
  );
  panel.querySelectorAll<HTMLElement>("#autoTheme .chip").forEach((b) =>
    b.addEventListener("click", () => {
      S.auto = b.dataset.v as Site["auto"];
      save(S);
      applyTheme();
    }),
  );

  const toggle = (open?: boolean) => panel.classList.toggle("open", open);
  fab.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle();
  });
  document.addEventListener("click", (e) => {
    if (!(e.target as HTMLElement).closest("#palettePanel, #paletteBtn")) toggle(false);
  });
}

applyTheme();
wirePalette();
