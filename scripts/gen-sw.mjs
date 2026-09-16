// Генерируется после `astro build` + `pagefind`: сканирует dist/ и пишет
// dist/sw.js с precache-манифестом (оболочка приложения) + dist/precache/*.json
// (списки страниц и картинок по аркам — для кнопки «скачать арку офлайн»).
//
// Стратегии в самом sw.js:
//   • навигация (HTML)        — network-first, затем кэш, затем /offline/
//   • /_astro/*.{js,css,woff2} и /pagefind/* — cache-first (иммутабельно, с хэшем)
//   • /_astro/*.{webp,avif,png,jpg} — cache-first, но НЕ в precache (тяжёлые)
// Версия кэша = хэш от списка precache: новый билд → новый кэш, старый чистится.

import { readdir, readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import { join, relative, sep, posix } from "node:path";

const DIST = "dist";

async function walk(dir) {
  const out = [];
  for (const name of await readdir(dir)) {
    const p = join(dir, name);
    const s = await stat(p);
    if (s.isDirectory()) out.push(...(await walk(p)));
    else out.push(p);
  }
  return out;
}

const toUrl = (p) => "/" + relative(DIST, p).split(sep).join(posix.sep);

const files = await walk(DIST);
const urls = files.map(toUrl);

// ── оболочка приложения: precache на install ──
const shell = new Set(["/", "/extra/", "/offline/", "/search/", "/manifest.webmanifest"]);
for (const u of urls) {
  if (/^\/_astro\/.*\.(js|css|woff2?)$/.test(u)) shell.add(u);
  if (/^\/pagefind\/(pagefind(-ui)?\.(js|css)|.*\.wasm.*|pagefind-.*\.js)$/.test(u))
    shell.add(u);
  if (/^\/arc\/[^/]+\/index\.html$/.test(u)) shell.add(u.replace(/index\.html$/, ""));
  if (/^\/(icon-\d+\.png|favicon\.\w+)$/.test(u)) shell.add(u);
}

// ── карта арок + «Дополнительного» (одним пакетом, как ещё одна «арка»):
//    страницы глав + их картинки, для кнопки «скачать офлайн» ──
const arcs = {};
const IMG_RE = /(?:src|href)="(\/_astro\/[^"]+\.(?:webp|avif|png|jpe?g))"/g;
const SRCSET_RE = /srcset="([^"]+)"/g;
for (const p of files) {
  const u = toUrl(p);
  // страницы самих глав/частей — как и было
  let m = u.match(/^\/read\/(arc-[^/]+|extra)\/[^/]+\/index\.html$/);
  // + подменю конкретной истории «Дополнительного» (/extra/<slug>/ — список
  // частей многочастевой истории) — без этого клик по истории из офлайн-списка
  // на /extra вёл на несохранённую страницу, даже когда все главы уже скачаны
  if (!m) {
    const m2 = u.match(/^\/extra\/([^/]+)\/index\.html$/);
    if (m2) m = [u, "extra"];
  }
  if (!m) continue;
  const slug = m[1];
  (arcs[slug] ??= { pages: [], assets: new Set() });
  arcs[slug].pages.push(u.replace(/index\.html$/, ""));
  const html = await readFile(p, "utf8");
  let mm;
  while ((mm = IMG_RE.exec(html))) arcs[slug].assets.add(mm[1]);
  while ((mm = SRCSET_RE.exec(html)))
    for (const part of mm[1].split(","))
      if (/^\/_astro\//.test(part.trim()))
        arcs[slug].assets.add(part.trim().split(/\s+/)[0]);
}

await mkdir(join(DIST, "precache"), { recursive: true });
const arcIndex = {};
for (const [slug, v] of Object.entries(arcs)) {
  const payload = { slug, pages: v.pages.sort(), assets: [...v.assets].sort() };
  await writeFile(
    join(DIST, "precache", `${slug}.json`),
    JSON.stringify(payload),
  );
  arcIndex[slug] = { pages: v.pages.length, assets: v.assets.size };
}

const SHELL = [...shell].sort();
const BUILD_ID = createHash("sha1")
  .update(SHELL.join("\n"))
  .digest("hex")
  .slice(0, 12);

await writeFile(
  join(DIST, "precache", "index.json"),
  JSON.stringify({ buildId: BUILD_ID, arcs: arcIndex }),
);

const SW = `// СГЕНЕРИРОВАНО scripts/gen-sw.mjs — не редактировать вручную.
const BUILD = ${JSON.stringify(BUILD_ID)};
const CACHE = "rezero-" + BUILD;
const SHELL = ${JSON.stringify(SHELL)};

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(
        ks.filter((k) => k.startsWith("rezero-") && k !== CACHE).map((k) => caches.delete(k)),
      ))
      .then(() => self.clients.claim())
      .then(() => self.clients.matchAll())
      .then((cs) => cs.forEach((c) => c.postMessage({ type: "sw-updated", build: BUILD }))),
  );
});

const isImmutable = (u) =>
  /^\\/_astro\\/.*\\.(webp|avif|png|jpe?g|js|css|woff2?)$/.test(u) ||
  u.startsWith("/pagefind/");

self.addEventListener("fetch", (e) => {
  const { request } = e;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;

  // навигации — network-first, затем кэш, затем офлайн-страница.
  // Важно: fetch() резолвится (не падает в catch), даже если сервер ответил
  // ошибкой — плохое мобильное/поездное соединение нередко всё же достукивается
  // до Cloudflare, но получает 5xx/капчу капчпортала вместо страницы. Без
  // проверки res.ok сервис-воркер принимал такой ответ за «успех», показывал
  // и даже кэшировал его поверх рабочей офлайн-копии.
  //
  // Если для страницы уже есть кэш — не ждём медленную/шаткую сеть дольше
  // пары секунд, раз готовый ответ и так под рукой (короткий таймаут).
  // Если кэша нет (первый заход), упасть всё равно некуда, кроме общей
  // офлайн-заглушки — но и ждать сеть бесконечно тоже плохо: у части
  // читателей соединение до конкретно этого сервера настолько нестабильно,
  // что зависшая страница хуже, чем быстрый явный «нет сети» — поэтому тут
  // таймаут длиннее (обычному чуть медленному интернету хватит с запасом),
  // но не бесконечный.
  if (request.mode === "navigate") {
    e.respondWith(
      caches.match(request).then((cached) => {
        // redirect: "manual" — ссылки на сайте без завершающего слэша (обычные
        // href вида /arc/arc-01) сервер отвечает 307 на /arc/arc-01/. Обычный
        // fetch() САМ незаметно проходит по этому редиректу, и тогда итоговый
        // Response помечен как redirected=true — а браузер запрещает отвечать
        // таким объектом на навигацию и молча отменяет её (DevTools покажет
        // «(canceled)», 0мс, без единого намёка на причину). С "manual" редирект
        // возвращается как opaqueredirect и передаётся браузеру как есть — тот
        // сам совершает переход на /arc/arc-01/, и уже на этот адрес прилетает
        // новое, отдельное событие fetch без всякого редиректа.
        const net = fetch(request, { redirect: "manual" }).then((res) => {
          if (res.type === "opaqueredirect") return res;
          if (!res.ok) throw new Error("bad status " + res.status);
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
          return res;
        });
        const timeout = (ms, fallback) =>
          new Promise((resolve) => setTimeout(() => resolve(fallback), ms));
        if (!cached) {
          return Promise.race([net, timeout(12000, null)]).then(
            (res) => res || caches.match("/offline/"),
          ).catch(() => caches.match("/offline/"));
        }
        return Promise.race([net, timeout(4000, cached)]).catch(() => cached);
      }),
    );
    return;
  }

  // хэшированные ассеты — cache-first
  if (isImmutable(url.pathname)) {
    e.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((res) => {
            const copy = res.clone();
            if (res.ok) caches.open(CACHE).then((c) => c.put(request, copy));
            return res;
          }),
      ),
    );
    return;
  }

  // прочее (json Pagefind-фрагментов и т.п.) — stale-while-revalidate
  e.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const hit = await cache.match(request);
      const net = fetch(request)
        .then((res) => {
          if (res.ok) cache.put(request, res.clone());
          return res;
        })
        .catch(() => hit);
      return hit || net;
    }),
  );
});

// «скачать арку офлайн»: клиент шлёт список URL, кладём в текущий кэш
self.addEventListener("message", (e) => {
  const d = e.data || {};
  if (d.type === "cache-urls" && Array.isArray(d.urls)) {
    e.waitUntil(
      caches.open(CACHE).then(async (c) => {
        let done = 0;
        for (const u of d.urls) {
          try {
            await c.add(u);
          } catch {}
          done++;
          if (done % 20 === 0 || done === d.urls.length)
            e.source && e.source.postMessage({ type: "cache-progress", done, total: d.urls.length });
        }
        e.source && e.source.postMessage({ type: "cache-done", total: d.urls.length });
      }),
    );
  }
  if (d.type === "skip-waiting") self.skipWaiting();
});
`;

await writeFile(join(DIST, "sw.js"), SW);
console.log(
  `sw.js: build ${BUILD_ID}, оболочка ${SHELL.length} файлов, ` +
    `арок в карте ${Object.keys(arcIndex).length}`,
);
