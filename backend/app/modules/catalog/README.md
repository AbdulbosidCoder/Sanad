# Модуль `catalog`

Категории, бренды, товары и их варианты, фото товара со всех сторон (от продавца и от покупателей), модерация, фильтры витрины.

## Связи

**Зависит от (вызывает их `service.py`):**
- `stores` — доступ продавца (`store_access`), какие магазины активны, название магазина в карточке
- `media` — загрузка файлов (позже; сейчас фото — это URL)
- `audit` — (позже)

**Используется модулями:** `inventory` (список вариантов магазина, флаг «в наличии»), `i18n` (текст оригинала, события), позже `search`, `cart`, `reviews`, `engagement`, `recommendations`

**Публикует события:** `ProductCreated`, `ProductUpdated`, `ProductArchived` (пока только в лог)

**Таблицы:** `categories`, `brands`, `products`, `product_variants`, `product_images`

## Эндпоинты

| Метод | Путь | Кто | Что делает |
|---|---|---|---|
| GET | `/categories` | все | Дерево категорий на языке запроса (`?lang=` или `Accept-Language`) с числом товаров |
| GET | `/brands?category=` | все | Бренды; с `category` — только те, у кого там есть товары |
| GET | `/catalog/filters?category=` | все | Всё для кнопок-фильтров: подкатегории, бренды с количеством, диапазон цен, размеры |
| GET | `/products` | все | Каталог: `q, category, brand (несколько), store, size (несколько), price_min, price_max, in_stock, rating_min, sort=newest\|price_asc\|price_desc\|popular\|rating, cursor, limit` |
| GET | `/products/{slug}` | все | Карточка: варианты, фото продавца по сторонам, одобренные фото покупателей, `photo_coverage` |
| POST | `/products/{id}/buyer-photos` | вошедший | Фото покупателя; видно после модерации |
| GET/POST | `/seller/products` | сотрудник / `products.write` | Товары магазина; создание сразу с вариантами (черновик) |
| GET/PATCH | `/seller/products/{id}` | то же | Товар |
| POST | `/seller/products/{id}/publish` \| `/archive` | `products.write` | Публикация: нужен активный вариант с ценой и хотя бы одно фото |
| DELETE | `/seller/products/{id}` | `products.delete` | Мягкое удаление |
| POST/PATCH/DELETE | `/seller/products/{id}/variants[/{vid}]` | `products.write` | Варианты (размер/цвет, цена, старая цена) |
| POST/DELETE | `/seller/products/{id}/images[/{iid}]` | `products.write` | Фото стороны `left, right, top, sole, inside, back, label` (или `other`); новое фото той же стороны заменяет старое |
| GET/POST/PATCH | `/admin/categories[/{id}]`, `/admin/brands[/{id}]` | `catalog.manage` | Справочники; названия категорий на трёх языках |
| POST | `/admin/products/{id}/moderate` | 🔒 `products.moderate` | `block` скрывает товар и запрещает публикацию, `unblock` возвращает в черновик |
| POST | `/admin/product-images/{id}/moderate` | `products.moderate` | Одобрить/отклонить фото покупателя |

## Правила

- Покупатель видит товар, только если он `active`, не удалён и магазин активен.
- `products.min_price` и `products.in_stock` — сводка по активным вариантам; её пересчитывает сервис при изменении вариантов, а `inventory` — при изменении остатков. Поэтому фильтр «в наличии» и сортировка по цене не лезут в таблицы других модулей.
- Фильтр `size=42&in_stock=true` ищет товары, где в наличии именно размер 42.
- `photo_coverage` показывает, каких из 7 сторон не хватает — для бейджа «Фото со всех сторон» и будущей AI-проверки подлинности (поле `ai_check` у каждого фото).
- Деньги в ответах — строки (`"1450000.00"`), валюта `UZS`.

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и его связей |
| `api.py` | HTTP-эндпоинты |
| `service.py` | Бизнес-логика; для `inventory` — `store_variants`, `set_variant_in_stock` |
| `repository.py` | Запросы к БД, фильтры каталога |
| `models.py` | Таблицы, список сторон фото |
| `schemas.py` | Тела запросов/ответов |

## Ещё не сделано

- Переводы названий и описаний товаров на uz/ru/en — этап 3 (`i18n`). Сейчас товар хранит оригинал (`source_locale`).
- Загрузка фото файлом через presigned URL — модуль `media`.
- Фото покупателя только после покупки — когда появятся заказы (этап 5).
- Полнотекстовый поиск и автодополнение — этап 4 (`search`); сейчас `q` ищет подстроку в названии и бренде.
- Отдельная таблица скидок; сейчас скидка = `compare_at_price` у варианта.

## Где искать баг

Симптомы: товар не создаётся или не публикуется, нет на витрине, неверная цена, фильтр показывает не то, нет категории или бренда.

В ошибке API и в логах ищите `"module": "catalog"` и `request_id`. Не видно товара на витрине → проверьте его `status`, `deleted_at` и статус магазина.
