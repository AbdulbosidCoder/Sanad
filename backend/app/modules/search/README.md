# Модуль `search`

Поиск товаров на всех трёх языках сразу, с префиксами («zorb run») и опечатками
(«nikee»), подсказки при наборе, история поиска покупателя, популярные запросы.

## Связи

**Зависит от:** `catalog` (поля товара, карточки, фильтры), `i18n` (тексты переводов)

**Публикует:** `SearchPerformed` (для аналитики) · **Слушает:** `ProductCreated`,
`ProductUpdated`, `ProductArchived`, `TranslationReady` — переиндексирует товар

**Таблицы:** `search_documents`, `search_history`

## Как это работает

- `search_documents.document` — весь текст товара одной строкой в нижнем регистре:
  название, бренд, категория и её родители (uz/ru/en), описание, все переводы.
- `tsv` — генерируемый столбец `to_tsvector('simple', document)` с GIN-индексом:
  каждое слово запроса ищется как префикс (`nike:* & air:*`).
- Индекс триграмм (`pg_trgm`) по `document` ловит опечатки (`запрос <% document`).
- Ранг = `ts_rank` + `word_similarity`. Сортировка по умолчанию — `relevance`.
- В `setup()` поиск подключается к каталогу (`catalog.set_search_matcher`), поэтому
  `GET /products?q=` тоже ищет по индексу. Видимость (активный товар, магазин не
  заблокирован) проверяет каталог.

Переименовали бренд или категорию → индекс старый, пока товар не изменится. Для этого
есть `POST /admin/search/reindex` (право `ops.jobs_retry`). `python -m app.seed` строит
индекс сам, если он пуст.

## API

| Метод | Путь | Кто | Что |
|---|---|---|---|
| GET | `/search?q=&category=&brand=&size=&price_min=&price_max=&in_stock=&sort=` | все | Поиск; первая страница записывается в историю (если вошёл) |
| GET | `/search/suggest?q=` | все | Подсказки: своя история, бренды, категории, товары |
| GET | `/search/popular` | все | Топ запросов за 7 дней |
| GET / DELETE | `/me/search-history` (`?q=` — один запрос) | покупатель | История |
| POST | `/admin/search/reindex` | `ops.jobs_retry` | Перестроить индекс |

## Где искать ошибку

- Товар не находится: `select document from search_documents where product_id=…` —
  есть ли строка и нужные слова. Нет строки → `POST /admin/search/reindex`.
- Находится, но не показывается: товар не `active` или магазин заблокирован (каталог).
