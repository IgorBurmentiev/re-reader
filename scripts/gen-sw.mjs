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

// ── обложки/фоны на главной, /extra/ и странице каждой арки ──
// эти картинки не относятся ни к одной конкретной главе, поэтому их не
// подхватывает сканирование ниже (оно смотрит только внутрь страниц самих
// глав) — без этого при полностью офлайновом заходе (даже после «скачать
// арку целиком») обложка арки на / и её же фоновая картинка на /arc/<slug>/
// оставались пустыми, хотя сам текст и картинки глав открывались нормально.
//
// ВАЖНО: сканировать тут можно только строго ограниченные куски разметки —
// hero-картинку (единственный <img class="bg">) и карточки (<div
// class="cover">...</div>) — а НЕ всю страницу целиком: страницы арок и
// «Дополнительного» также содержат полные фото-галереи (сотни картинок),
// и попытка вытащить из HTML вообще все /_astro/*.webp раздула shell с
// полусотни файлов до 3000+ и утянула бы в обязательную установку для
// каждого нового читателя фактически все иллюстрации сайта разом.
const COVER_SRC_RE = /(?:src|href)="(\/_astro\/[^"]+\.(?:webp|avif|png|jpe?g))"/g;
const COVER_SRCSET_RE = /srcset="([^"]+)"/g;
function collectImages(fragment) {
  let mm;
  while ((mm = COVER_SRC_RE.exec(fragment))) shell.add(mm[1]);
  while ((mm = COVER_SRCSET_RE.exec(fragment)))
    for (const part of mm[1].split(","))
      if (/^\/_astro\//.test(part.trim())) shell.add(part.trim().split(/\s+/)[0]);
}
const coverPages = ["index.html", "extra/index.html"];
for (const u of urls) {
  if (/^\/arc\/[^/]+\/index\.html$/.test(u)) coverPages.push(u.slice(1));
}
for (const rel of coverPages) {
  let html;
  try {
    html = await readFile(join(DIST, rel), "utf8");
  } catch {
    continue;
  }
  const hero = html.match(/<img[^>]*\sclass="bg"[^>]*>/);
  if (hero) collectImages(hero[0]);
  for (const m of html.matchAll(/<div class="cover"[^>]*>.*?<\/div>/g)) collectImages(m[0]);
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
      .then((ks) => {
        const stale = ks.filter((k) => k.startsWith("rezero-") && k !== CACHE);
        // тост «обновление загружено» имеет смысл только если реально была
        // предыдущая версия кэша — на самом первом визите (stale пуст) это
        // не обновление, а обычная установка, и врать про «обновление»
        // новому читателю незачем.
        const isRealUpdate = stale.length > 0;
        return Promise.all(stale.map((k) => caches.delete(k))).then(() => isRealUpdate);
      })
      .then((isRealUpdate) =>
        self.clients.claim().then(() => {
          if (!isRealUpdate) return;
          return self.clients.matchAll()
            .then((cs) => cs.forEach((c) => c.postMessage({ type: "sw-updated", build: BUILD })));
        }),
      ),
  );
});

const isImmutable = (u) =>
  /^\\/_astro\\/.*\\.(webp|avif|png|jpe?g|js|css|woff2?)$/.test(u) ||
  u.startsWith("/pagefind/");

// самый последний рубеж: если ДАЖЕ /offline/ вдруг не нашёлся в кэше
// (например браузер под нехваткой места сам подчистил кэш сайта, а сеть в
// этот момент недоступна) — respondWith() ни в коем случае не должен
// получить undefined. Такое приводит не к нашей странице "Нет сети", а к
// голой сетевой ошибке браузера — с виду будто сайт вообще сломан. Этот
// текст ни от чего не зависит (без внешних шрифтов/стилей), поэтому
// сработает, даже если весь остальной кэш каким-то образом пуст.
const LAST_RESORT_HTML = "<!doctype html><meta charset=utf-8>" +
  "<meta name=viewport content=\\"width=device-width,initial-scale=1\\">" +
  "<body style=\\"font:16px system-ui,sans-serif;background:#161116;color:#e8dfe0;" +
  "max-width:30rem;margin:12vh auto;padding:0 20px;text-align:center\\">" +
  "<h1 style=\\"font-weight:400\\">Нет сети</h1>" +
  "<p>Не получилось ни загрузить страницу, ни найти сохранённую офлайн-копию. " +
  "Проверьте подключение и обновите страницу.</p>" +
  "<p><a href=\\"/\\" style=\\"color:#c9a15a\\">на заглавную</a></p>";

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
    // все сохранённые страницы лежат под каноническим адресом со слэшем
    // (/arc/arc-01/), а реальные ссылки на сайте — без него (/arc/arc-01).
    // Онлайн это чинит редирект (см. ниже), но офлайн его взять неоткуда:
    // клик по такой ссылке без сети должен всё равно найти уже скачанную
    // страницу, а не считать её «не скачанной» только из-за слэша.
    const matchWithSlash = (req) =>
      caches.match(req).then((hit) => {
        if (hit || req.url.endsWith("/")) return hit;
        return caches.match(req.url + "/");
      });
    e.respondWith(
      matchWithSlash(request).then((cached) => {
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
        const lastResort = () =>
          new Response(LAST_RESORT_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
        if (!cached) {
          return Promise.race([net, timeout(12000, null)])
            .then((res) => res || caches.match("/offline/"))
            .catch(() => caches.match("/offline/"))
            .then((res) => res || lastResort());
        }
        return Promise.race([net, timeout(4000, cached)]).catch(() => cached || lastResort());
      }),
    );
    return;
  }

  // хэшированные ассеты — cache-first.
  // ignoreVary — сервер (замечено на astro preview, но не факт что только там)
  // шлёт заголовок "Vary: Origin" на статику; браузер сам решает, слать ли заголовок
  // Origin, и делает это по-разному для module-script'ов (cors) и обычных
  // fetch()/<link> (no-cors) — из-за этого Cache API считает такие запросы
  // РАЗНЫМИ и не находит совпадение, хотя URL один и тот же байт-в-байт файл.
  // Офлайн это означало «не найдено в кэше» → настоящий сетевой fetch → падает
  // с ERR_FAILED (главы грузились без reader.ts: не работал ни прогресс, ни
  // оглавление, ни настройки читалки). Хэшированный неизменяемый ассет по
  // определению не может отличаться в зависимости от Vary — эти заголовки
  // при сверке кэша просто не имеют смысла для таких файлов.
  if (isImmutable(url.pathname)) {
    e.respondWith(
      caches.match(request, { ignoreVary: true }).then(
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

// «скачать арку офлайн»: клиент шлёт список URL, кладём в текущий кэш.
// Ошибка на отдельном файле не должна ронять весь процесс (одна битая
// картинка не должна блокировать остальные 400 страниц) — но и молчать о
// провале нельзя: раньше пустой catch проглатывал вообще все ошибки, и клиент
// получал «готово», даже если реально не скачалось НИЧЕГО (например, кликнули
// «скачать» без сети) — ложная уверенность хуже честной ошибки.
self.addEventListener("message", (e) => {
  const d = e.data || {};
  if (d.type === "cache-urls" && Array.isArray(d.urls)) {
    e.waitUntil(
      caches.open(CACHE).then(async (c) => {
        let done = 0;
        let failed = 0;
        for (const u of d.urls) {
          try {
            await c.add(u);
          } catch {
            failed++;
          }
          done++;
          if (done % 20 === 0 || done === d.urls.length)
            e.source && e.source.postMessage({ type: "cache-progress", done, total: d.urls.length, failed });
        }
        e.source && e.source.postMessage({ type: "cache-done", total: d.urls.length, failed });
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
