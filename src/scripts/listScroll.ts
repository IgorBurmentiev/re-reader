// Запоминает прокрутку списковых страниц (главная, /extra, страница арки) и
// восстанавливает её при возврате кнопкой «назад» — вместо того чтобы
// полагаться на нативное восстановление браузера, которое здесь вело себя
// непоследовательно (иногда работает, иногда кидает в начало страницы).
// Восстанавливаем только при настоящей навигации назад/вперёд (Navigation
// Timing API), чтобы обычный переход по ссылке всегда начинался сверху.
export function initListScroll(): void {
  const KEY = "listpos:" + location.pathname;

  try {
    const nav = performance.getEntriesByType("navigation")[0] as
      | PerformanceNavigationTiming
      | undefined;
    if (nav?.type === "back_forward") {
      const y = Number(localStorage.getItem(KEY) || 0);
      if (y > 80) {
        setTimeout(() => scrollTo(0, y), 60);
      }
    }
  } catch {
    /* Navigation Timing недоступен — просто не восстанавливаем */
  }

  let raf = 0;
  addEventListener(
    "scroll",
    () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        try {
          localStorage.setItem(KEY, String(scrollY));
        } catch {
          /* localStorage недоступен (приватный режим и т.п.) — не критично */
        }
      });
    },
    { passive: true },
  );
}
