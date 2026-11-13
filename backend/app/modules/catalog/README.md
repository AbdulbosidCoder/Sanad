# Модуль `catalog`

Товары, варианты, категории, бренды, изображения, скидки.

## Связи

**Зависит от (вызывает их `service.py`):**
- `stores`
- `media`
- `audit`

**Используется модулями:**
- `i18n`
- `inventory`
- `search`
- `cart`
- `reviews`
- `engagement`
- `recommendations`

**Публикует события:**
- `ProductCreated`
- `ProductUpdated`
- `ProductArchived`

**Слушает события:**
- —

**Таблицы:** `products`, `product_variants`, `categories`, `brands`, `product_images`, `discounts`

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и его связей (видно в `GET /api/v1/system/modules`) |
| `api.py` | HTTP-эндпоинты: принимают запрос, проверяют права, вызывают `service.py` |
| `service.py` | Бизнес-логика. Единственная точка входа для других модулей |
| `events.py` | События, которые модуль публикует и на которые подписан |
| `models.py`, `repository.py`, `schemas.py` | Появятся вместе с функциональностью |

## Где искать баг

Симптомы, которые обычно ведут сюда: товар не создаётся или не сохраняется, неверная цена, нет категории.

В ошибке API и в логах ищите `"module": "catalog"` и `request_id`.
