// Общая логика кнопки «скачать для офлайна» — используется и на /extra, и на
// страницах арок. Помимо самого скачивания:
//  · кнопка запоминает не факт скачивания, а «отпечаток» списка страниц/картинок
//    (precache/<slug>.json) — при повторном заходе, если содержимое арки/
//    «Дополнительного» не изменилось, кнопка сразу неактивна («сохранено»),
//    и лишний клик просто невозможен; если вышли новые главы — отпечаток не
//    совпадёт, кнопка сама снова станет активной с пометкой «есть новое»;
//  · клик офлайн (нет сети) раньше вешал кнопку на «загрузка…» навсегда —
//    теперь ошибка ловится, кнопка возвращается в рабочее состояние с понятным
//    сообщением, можно просто попробовать ещё раз при подключении.
function safe<T>(fn: () => T): T | undefined {
  try {
    return fn();
  } catch {
    return undefined;
  }
}

function hashStr(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return h.toString(36);
}

// раньше "скачано ✓" верило один раз сохранённой сигнатуре и никогда больше
// не проверяло, что файлы физически ещё лежат в кэше — а браузер вправе сам
// тихо стереть офлайн-кэш при нехватке места на устройстве. Из-за этого
// кнопка могла годами утверждать «сохранено», хотя часть (или всё) уже
// потерялось. Здесь — честная проверка по факту: реально ли каждый URL из
// списка всё ещё отвечает из Cache Storage.
async function verifyCached(urls: string[]): Promise<boolean> {
  if (!("caches" in window)) return false;
  const keys = await caches.keys();
  const cacheName = keys.find((k) => k.startsWith("rezero-"));
  if (!cacheName) return false;
  const cache = await caches.open(cacheName);
  const hits = await Promise.all(urls.map((u) => cache.match(u).then((r) => !!r)));
  return hits.every(Boolean);
}

export function initOfflineDownload(buttonId: string, doneLabel: string): void {
  const off = document.getElementById(buttonId) as HTMLButtonElement | null;
  if (!off) return;
  const oslug = off.dataset.offlineSlug || off.dataset.slug;
  const OFFKEY = `rz:offline:${oslug}`;

  // при заходе на страницу — если офлайн, fetch просто тихо не сработает и
  // кнопка останется в своём стартовом виде из разметки
  fetch(`/precache/${oslug}.json`)
    .then((r) => r.text())
    .then(async (text) => {
      const sig = hashStr(text);
      const saved = safe(() => JSON.parse(localStorage.getItem(OFFKEY) || "null"));
      if (saved?.sig === sig) {
        const data = JSON.parse(text);
        const intact = await verifyCached([...data.pages, ...data.assets]);
        if (intact) {
          off.textContent = doneLabel;
          off.disabled = true;
        } else {
          off.textContent = "часть офлайн-копии пропала (не хватает места на устройстве?) — нажмите, чтобы докачать";
          off.disabled = false;
        }
      } else if (saved) {
        off.textContent = "обновить офлайн-копию — вышло новое";
        off.disabled = false;
      }
    })
    .catch(() => {});

  off.addEventListener("click", async () => {
    let sw = navigator.serviceWorker?.controller;
    // на самом первом визите на сайт страница может отрисоваться и стать
    // кликабельной раньше, чем сервис-воркер успевает встать под управление
    // (регистрация + install + activate — доля секунды, но клик может
    // случиться раньше). Без этой подстраховки в такой момент показывалось
    // "доступно только в собранной версии" — неправда, версия та самая,
    // просто воркер ещё не готов.
    if (!sw && navigator.serviceWorker) {
      off.textContent = "секунду…";
      // "ready" резолвится, когда воркер стал active — но это не то же самое,
      // что "уже взял эту вкладку под контроль" (controller всё ещё может
      // быть null в этот самый момент, событие controllerchange прилетает
      // чуть позже отдельно). Ждём именно controllerchange, а не ready.
      sw = await new Promise<ServiceWorker | null>((resolve) => {
        const onChange = () => {
          navigator.serviceWorker.removeEventListener("controllerchange", onChange);
          resolve(navigator.serviceWorker.controller);
        };
        navigator.serviceWorker.addEventListener("controllerchange", onChange);
        setTimeout(() => {
          navigator.serviceWorker.removeEventListener("controllerchange", onChange);
          resolve(navigator.serviceWorker.controller);
        }, 5000);
      });
    }
    if (!sw) {
      off.textContent = navigator.serviceWorker
        ? "офлайн-кэш ещё не готов — обновите страницу и попробуйте снова"
        : "офлайн-кэш доступен только в собранной версии";
      off.disabled = false;
      return;
    }
    off.disabled = true;
    off.textContent = "загрузка…";
    try {
      const text = await fetch(`/precache/${oslug}.json`).then((r) => r.text());
      const sig = hashStr(text);
      const data = JSON.parse(text);
      const urls = [...data.pages, ...data.assets];
      const failed = await new Promise<number>((resolve) => {
        const onMsg = (e: MessageEvent) => {
          const m = e.data || {};
          if (m.type === "cache-progress") off.textContent = `загрузка… ${m.done}/${m.total}`;
          if (m.type === "cache-done") {
            navigator.serviceWorker.removeEventListener("message", onMsg);
            resolve(m.failed || 0);
          }
        };
        navigator.serviceWorker.addEventListener("message", onMsg);
        sw.postMessage({ type: "cache-urls", urls });
      });
      if (failed > 0) {
        // не отмечаем как готово и не сохраняем сигнатуру — иначе кнопка
        // навсегда решит, что всё скачано, хотя часть файлов не долетела
        off.textContent = `не всё скачалось (${failed} из ${urls.length}) — нажмите ещё раз при связи получше`;
        off.disabled = false;
        return;
      }
      off.textContent = doneLabel;
      off.disabled = true;
      safe(() => localStorage.setItem(OFFKEY, JSON.stringify({ sig, ts: Date.now() })));
    } catch {
      off.textContent = "не получилось — проверьте связь и нажмите ещё раз";
      off.disabled = false;
    }
  });
}
