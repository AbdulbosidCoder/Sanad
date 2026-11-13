# Модуль `inventory`

Остатки, резервы под заказы, движение склада, low-stock.

## Связи

**Зависит от (вызывает их `service.py`):**
- `catalog`

**Используется модулями:**
- `cart`
- `orders`

**Публикует события:**
- `StockLow`
- `StockReserved`

**Слушает события:**
- `OrderPlaced`
- `PaymentSucceeded`
- `OrderCancelled`
- `RefundCompleted`

**Таблицы:** `inventory`, `stock_reservations`, `stock_movements`

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и его связей (видно в `GET /api/v1/system/modules`) |
| `api.py` | HTTP-эндпоинты: принимают запрос, проверяют права, вызывают `service.py` |
| `service.py` | Бизнес-логика. Единственная точка входа для других модулей |
| `events.py` | События, которые модуль публикует и на которые подписан |
| `models.py`, `repository.py`, `schemas.py` | Появятся вместе с функциональностью |

## Где искать баг

Симптомы, которые обычно ведут сюда: неверный остаток, «нет в наличии», хотя товар есть, остаток ушёл в минус.

В ошибке API и в логах ищите `"module": "inventory"` и `request_id`.
