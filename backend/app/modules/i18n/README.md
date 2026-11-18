# Модуль `i18n`

Переводы товаров на uz / ru / en. Продавец пишет товар на одном языке (`source_locale`),
остальные два языка переводятся автоматически в фоне. Оригинал никогда не меняется,
перевод продавец может поправить вручную.

## Связи

**Зависит от (вызывает их `service.py`):**
- `catalog` — текст оригинала (`product_source`), подключение переводов к витрине (`set_translation_lookup`)
- `stores` — доступ продавца (`store_access`)

**Используется модулями:** `catalog` (через подключённую функцию `lookup`), позже `search`

**Публикует события:** `TranslationReady` (перевод на язык записан/изменён — поиск переиндексирует)

**Слушает события:** `ProductCreated`, `ProductUpdated` (изменились название/описание/язык)

**Таблицы:** `product_translations`, `translation_jobs`

## Как это работает

1. Продавец создал или поменял текст товара → catalog публикует событие.
2. В той же транзакции создаётся задача `translation_jobs` для каждого другого языка
   (одна активная задача на товар+язык — уникальный частичный индекс).
3. Воркер `i18n.translate_pending` (каждую минуту) берёт задачи (`FOR UPDATE SKIP LOCKED`),
   переводит и пишет `product_translations` с `origin=machine`.
4. Витрина (`GET /products`, `GET /products/{slug}`) по `?lang=` или `Accept-Language`
   показывает перевод; если перевода нет — оригинал.

Ручной перевод (`origin=manual`) машина не перезаписывает. Если продавец потом поменял
оригинал, у ручного перевода ставится `needs_review=true` — нужно проверить.

## Движок перевода

| `TRANSLATOR` | Что делает |
|---|---|
| `none` (по умолчанию) | Ничего не переводит, задачи после 5 попыток → `failed`, витрина показывает оригинал |
| `claude` | Claude API, нужен `ANTHROPIC_API_KEY`; модель — `TRANSLATION_MODEL` |

Ключ кладётся только в свой `.env`, в git его не коммитить. Демо-данные (`python -m app.seed`)
уже содержат uz/en переводы 10 товаров, поэтому переключение языка можно проверить без ключа.

## API

| Метод | Путь | Кто | Что |
|---|---|---|---|
| GET | `/seller/products/{id}/translations` | сотрудник магазина | 3 языка: `original` / `machine` / `manual` / `pending` / `missing` |
| PUT | `/seller/products/{id}/translations/{locale}` | `products.write` | Свой перевод (оригинал так менять нельзя → 409 `I18N.IS_ORIGINAL`) |
| POST | `/seller/products/{id}/translations/{locale}/retranslate` | `products.write` | Убрать ручной перевод и перевести заново |

## Где искать ошибку

- Перевод не появляется → `select status, attempts, last_error from translation_jobs where product_id=…`.
  `failed` с `no translator configured` — не задан `TRANSLATOR=claude`.
- Работает ли воркер: в логах `translations done`.
- Витрина показывает не тот язык → проверить `?lang=` и `product_translations.locale`.

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и связей |
| `api.py` | Эндпоинты продавца |
| `service.py` | Подписки на события, воркер, ручные правки |
| `translators.py` | Движки перевода (`NoTranslator`, `ClaudeTranslator`), подмена в тестах |
| `models.py`, `repository.py`, `schemas.py` | Таблицы, запросы, тела запросов/ответов |
| `tests/` | Тесты с детерминированным тестовым «переводчиком» |
