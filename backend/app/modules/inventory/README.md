# Модуль `inventory`

Остатки по вариантам товара, пороги low-stock и журнал всех движений склада.

## Связи

**Зависит от (вызывает их `service.py`):**
- `catalog` — варианты товаров магазина; сообщает каталогу, есть ли вариант в наличии
- `stores` — доступ продавца (`store_access`)

**Слушает события (этап 5):** `OrderPlaced`, `PaymentSucceeded`, `OrderCancelled`, `RefundCompleted`

**Таблицы:** `inventory`, `stock_movements` (`stock_reservations` — этап 5)

## Эндпоинты

| Метод | Путь | Кто | Что делает |
|---|---|---|---|
| GET | `/seller/inventory?low_stock=true` | сотрудник магазина | Остатки всех вариантов; с `low_stock` — только где `available <= порог`, самые пустые сверху |
| PATCH | `/seller/inventory/{variant_id}` | `inventory.write` | `on_hand` (задать) **или** `delta` (+10 пришло, −2 брак), `low_stock_threshold`, `note` |
| GET | `/seller/inventory/{variant_id}/movements` | сотрудник магазина | История изменений, новые сверху |

## Правила

- `available = on_hand - reserved`. `reserved` — товар, отложенный под неоплаченные заказы (этап 5); ниже него остаток опустить нельзя (`INVENTORY.BELOW_RESERVED`).
- Вариант без строки в `inventory` считается с остатком 0; строка появляется при первом изменении.
- Строка блокируется на время изменения (`SELECT ... FOR UPDATE`), каждое изменение пишется в `stock_movements` с автором и причиной (`manual`, `seed`, позже `sale`, `return`, `cancel`).

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и его связей |
| `api.py` | HTTP-эндпоинты |
| `service.py` | Бизнес-логика; `set_stock` для других модулей и демо-данных |
| `repository.py` | Запросы к БД |
| `models.py` | Таблицы |
| `schemas.py` | Тела запросов/ответов |

## Где искать баг

Симптомы: неверный остаток, товар «нет в наличии», хотя он есть, не работает low-stock.

В ошибке API и в логах ищите `"module": "inventory"`. Откуда взялось число — смотрите `GET /seller/inventory/{variant_id}/movements`.
