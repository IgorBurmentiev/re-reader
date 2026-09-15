// Общий тост «Открыто в Дополнительно» — одна и та же вёрстка/поведение на
// главной, на странице арки и на самой /extra (но НЕ в читалке — там сознательно
// не показываем, чтобы не отвлекать посреди чтения главы). CSS — в Base.astro
// (.unlock-toast), здесь только сборка и показ DOM-узла.

export function showUnlockToast(titles: string[], extraCount: number): void {
  if (!titles.length) return;
  const bar = document.createElement("div");
  bar.className = "unlock-toast";
  const list = titles.join(", ") + (extraCount > 0 ? ` и ещё ${extraCount}` : "");
  bar.innerHTML =
    '<svg class="ic" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
    '<rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>' +
    '<path d="m9 15 2 2 4-4"/></svg>' +
    `<div><b>Открыто в «Дополнительно»</b><p>${list}</p><a href="/extra">перейти →</a></div>`;
  document.body.appendChild(bar);
  requestAnimationFrame(() => bar.classList.add("show"));
  setTimeout(() => {
    bar.classList.remove("show");
    setTimeout(() => bar.remove(), 400);
  }, 8000);
}

/** сравнивает newly-unlocked с сохранённым снимком и один раз показывает тост;
 *  на самом первом визите (когда снимка ещё нет) — молча запоминает и не шумит */
export function checkAndToastUnlocks(unlocked: Set<string>, titleOf: (slug: string) => string | undefined): void {
  const KEY = "rz:extra:unlocked";
  let known: string[] = [];
  try {
    known = JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {}
  const knownSet = new Set(known);
  const newly = [...unlocked].filter((s) => !knownSet.has(s));
  try {
    localStorage.setItem(KEY, JSON.stringify([...unlocked]));
  } catch {}
  if (!newly.length || !known.length) return;
  const titles = newly.map(titleOf).filter((t): t is string => !!t).slice(0, 3);
  if (titles.length) showUnlockToast(titles, newly.length - titles.length);
}
