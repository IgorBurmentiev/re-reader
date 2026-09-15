import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

// Главы лежат в /content/arc-NN/<slug>.md (вне src — их пишут конвертеры).
// id получается вида "arc-04/001", "arc-09/interlude-00".
const CHAPTER_TYPE = z.enum([
  "chapter",
  "prologue",
  "epilogue",
  "interlude",
  "side",
  "if",
  "extra",
]);

const chapters = defineCollection({
  // главы — arc-*/<slug>.md. Перечисляем только реальные имена глав явными
  // положительными масками: так служебные файлы (_synopsis.md, _ocr_review.md)
  // не попадают в коллекцию, и не срабатывает баг двойной загрузки glob-loader'а
  // при отрицательных масках (отсюда были предупреждения "Duplicate id").
  loader: glob({
    pattern: [
      "arc-*/[0-9]*.md",
      "arc-*/{prologue,epilogue,interlude,side,if,extra}-*.md",
    ],
    base: "./content",
  }),
  schema: z.object({
    arc: z.union([z.number(), z.string()]).transform(String),
    volume: z.number().optional(),
    phase: z.number().optional(),
    type: CHAPTER_TYPE,
    number: z.union([z.number(), z.string()]).transform(String).optional(),
    label: z.string().optional(),
    title: z.string().default(""),
    order_release: z.number().optional(),
    order_chrono: z.number().optional(),
    illustrations: z.array(z.string()).default([]),
    source: z.string().optional(),
    translator: z.string().optional(),
  }),
});

// Раздел «Дополнительно» — content/extra/<slug>[-NN].md, пишет
// tools/extra_epub_to_md.py. Отдельная схема: это не пронумерованные главы
// арки, а истории/серии со своей категорией и статусом перевода.
const EXTRA_CATEGORY = z.enum([
  "side", "if", "ex", "comic_alive", "birthday_emilia", "birthday_remram",
  "event", "twitter",
]);
const EXTRA_STATUS = z.enum(["ok", "no_translation", "partial", "soon"]);

const extra = defineCollection({
  // служебные файлы (_foreword.md, _*_ocr_review.md) не истории — исключаем
  // одной положительной маской (не глобом-массивом с "!", см. chapters выше)
  loader: glob({ pattern: "[!_]*.md", base: "./content/extra" }),
  schema: z.object({
    title: z.string().default(""),
    title_jp: z.string().optional(),
    category: EXTRA_CATEGORY,
    status: EXTRA_STATUS.default("ok"),
    part: z.number().optional(),
    parts_total: z.number().optional(),
    series_title: z.string().optional(),
    read_after_arc: z.number().optional(),
    read_after_container: z.string().optional(),
    tags: z.array(z.string()).default([]),
    translator: z.string().optional(),
    fanart: z.string().optional(),
    source_ref: z.string().optional(),
  }),
});

export const collections = { chapters, extra };
