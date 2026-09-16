import { computeUnlocked } from "../lib/unlock";
import { checkAndToastUnlocks } from "../lib/unlockToast";
import { initListScroll } from "./listScroll";

initListScroll();

declare global {
  interface Window {
    __EXTRA__: {
      chapterMeta: Record<string, { arc: string; number?: string; volume?: number }>;
      arcsMeta: Record<string, { structure: "ln" | "wn"; volumes: string; phases: { n: number; ranges: [number, number][] }[] }>;
    };
  }
}

function safe<T>(fn: () => T): T | undefined {
  try {
    return fn();
  } catch {
    return undefined;
  }
}

const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;

const progress: Record<string, number> = safe(() => JSON.parse(localStorage.getItem("rz:progress") || "{}")) || {};
const { chapterMeta, arcsMeta } = window.__EXTRA__;

const rows = [...document.querySelectorAll<HTMLElement>("[data-slug]")];
const items = rows.map((el) => ({
  slug: el.dataset.slug!,
  read_after: el.dataset.arc
    ? { arc: parseInt(el.dataset.arc, 10), container: el.dataset.container || null }
    : null,
}));
const unlocked = computeUnlocked(progress, chapterMeta, arcsMeta, items);

function unlockSortKey(el: HTMLElement): [number, number] {
  const arc = el.dataset.arc ? parseInt(el.dataset.arc, 10) : 999;
  const n = el.dataset.container?.match(/\d+/)?.[0];
  return [arc, n ? parseInt(n, 10) : 0];
}

const queue = $("#queue");
const qlist = $("#qlist");
const queued: { el: HTMLElement; key: [number, number] }[] = [];
let doneCount = 0;

rows.forEach((el) => {
  const status = el.dataset.status || "ok";
  const parts = (el.dataset.parts || "").split(",").filter(Boolean);
  const readCount = parts.filter((p) => (progress[`extra/${p}`] ?? 0) >= 0.9).length;
  const isRead = parts.length > 0 && readCount === parts.length;
  const isOpen = unlocked.has(el.dataset.slug!);

  let state: "read" | "open" | "locked" | "notr";
  if (status !== "ok") state = "notr";
  else if (isRead) state = "read";
  else if (isOpen) state = "open";
  else state = "locked";
  el.dataset.state = state;

  // у .exbook текст статуса — в .state (соседний с .parts, внутри .meta);
  // у обычной .row это сам .meta целиком
  const metaEl = el.querySelector(".state") || el.querySelector(".meta");
  if (metaEl) {
    if (state === "read") metaEl.textContent = "прочитано";
    else if (state === "notr") metaEl.textContent = status === "no_translation" ? "нет перевода" : status === "partial" ? "неполный перевод" : "скоро";
    else if (state === "open") metaEl.textContent = readCount > 0 ? `${readCount}/${parts.length}` : "начать";
    else metaEl.textContent = "закрыто";
  }

  if (state === "read") doneCount++;

  if (state === "locked") {
    el.remove();
    queued.push({ el, key: unlockSortKey(el) });
  }
});

// пустые подгруппы/категории (после того как все локальные пункты ушли в очередь) — прячем
document.querySelectorAll<HTMLElement>(".subgrp").forEach((g) => {
  if (!g.querySelector("[data-slug]")) g.hidden = true;
});
document.querySelectorAll<HTMLElement>("section.cat").forEach((sec) => {
  if (!sec.querySelector("[data-slug]")) sec.hidden = true;
});

if (queued.length) {
  queue.hidden = false;
  queued.sort((a, b) => a.key[0] - b.key[0] || a.key[1] - b.key[1]);
  $("#qcount").textContent = `${queued.length} ${plural(queued.length)}`;
  qlist.innerHTML = "";
  for (const { el } of queued) {
    // намеренно НЕ показываем, после какого тома/арки открывается — это
    // само по себе спойлер-намёк; только название и что оно закрыто
    const title = el.querySelector(".t, h4")?.textContent || el.dataset.slug || "";
    const row = document.createElement("div");
    row.className = "qrow";
    row.innerHTML =
      '<svg class="ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
      '<rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>' +
      `<span class="t">${esc(title)}</span>`;
    qlist.appendChild(row);
  }
}

function plural(n: number): string {
  const m = n % 10, m2 = n % 100;
  if (m === 1 && m2 !== 11) return "история";
  if ([2, 3, 4].includes(m) && ![12, 13, 14].includes(m2)) return "истории";
  return "историй";
}
function esc(s: string): string {
  return s.replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" })[c]!);
}

const total = rows.length;
const prog = $("#prog");
if (prog && total) prog.textContent = `прочитано ${Math.round((doneCount / total) * 100)}%`;

/* ─────────── галерея — тот же паттерн, что у арок ─────────── */
const gal = document.getElementById("gal");
const alb = document.getElementById("alb");
const albImg = alb?.querySelector("img") as HTMLImageElement | undefined;
const gitems = [...(gal?.querySelectorAll<HTMLElement>(".gitem") ?? [])];
gitems.forEach((b) => {
  b.addEventListener("click", () => {
    if (!b.classList.contains("shown")) {
      b.classList.add("shown");
      return;
    }
    const full = b.dataset.full || b.querySelector("img")?.src;
    if (full && albImg && alb) {
      albImg.src = full;
      alb.classList.add("open");
    }
  });
});
alb?.addEventListener("click", () => alb.classList.remove("open"));
addEventListener("keydown", (e) => {
  if (e.key === "Escape") alb?.classList.remove("open");
});
const gExpand = document.getElementById("galExpand");
const gReveal = document.getElementById("galReveal");
gExpand?.addEventListener("click", () => {
  const open = gal?.classList.toggle("all");
  gExpand.textContent = open ? "свернуть список" : `развернуть список (${gExpand.dataset.n})`;
});
gReveal?.addEventListener("click", () => {
  const anyHidden = gitems.some((b) => !b.classList.contains("shown"));
  gitems.forEach((b) => b.classList.toggle("shown", anyHidden));
  gReveal.textContent = anyHidden ? "скрыть все" : "показать все";
});

/* ─────────── уведомление о новых открытых историях (общий тост) ─────────── */
checkAndToastUnlocks(
  unlocked,
  (slug) => rows.find((r) => r.dataset.slug === slug)?.querySelector(".t, h4")?.textContent || undefined,
);

/* ─────────── скачать всё «Дополнительное» для офлайна — тот же приём, что у арок ─────────── */
{
  const off = document.getElementById("offline") as HTMLButtonElement | null;
  const oslug = off?.dataset.offlineSlug;
  const OFFKEY = `rz:offline:${oslug}`;
  if (off) {
    safe(() => {
      if (localStorage.getItem(OFFKEY)) off.textContent = "всё сохранено ✓";
    });
    off.addEventListener("click", async () => {
      const sw = navigator.serviceWorker?.controller;
      if (!sw) {
        off.textContent = "офлайн-кэш доступен только в собранной версии";
        return;
      }
      off.disabled = true;
      off.textContent = "загрузка…";
      const data = await fetch(`/precache/${oslug}.json`).then((r) => r.json());
      const urls = [...data.pages, ...data.assets];
      const onMsg = (e: MessageEvent) => {
        const m = e.data || {};
        if (m.type === "cache-progress") off.textContent = `загрузка… ${m.done}/${m.total}`;
        if (m.type === "cache-done") {
          off.textContent = "всё сохранено ✓";
          off.disabled = false;
          safe(() => localStorage.setItem(OFFKEY, String(Date.now())));
          navigator.serviceWorker.removeEventListener("message", onMsg);
        }
      };
      navigator.serviceWorker.addEventListener("message", onMsg);
      sw.postMessage({ type: "cache-urls", urls });
    });
  }
}

