# Модуль `orders`

Checkout, родительский заказ и заказы продавцов, статусы, возвраты товара.

## Связи

**Зависит от (вызывает их `service.py`):**
- `cart`
- `inventory`
- `payments`
- `stores`
- `audit`

**Используется модулями:**
- `reviews`
- `recommendations`
- `analytics`
- `support`

**Публикует события:**
- `OrderPlaced`
- `OrderCancelled`
- `SellerOrderStatusChanged`

**Слушает события:**
- `PaymentSucceeded`
- `PaymentFailed`
- `RefundCompleted`

**Таблицы:** `orders`, `seller_orders`, `order_items`, `order_status_history`, `return_requests`

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и его связей (видно в `GET /api/v1/system/modules`) |
| `api.py` | HTTP-эндпоинты: принимают запрос, проверяют права, вызывают `service.py` |
| `service.py` | Бизнес-логика. Единственная точка входа для других модулей |
| `events.py` | События, которые модуль публикует и на которые подписан |
| `models.py`, `repository.py`, `schemas.py` | Появятся вместе с функциональностью |

## Где искать баг

Симптомы, которые обычно ведут сюда: заказ не создаётся, неверный статус, заказ не разделился по продавцам.

В ошибке API и в логах ищите `"module": "orders"` и `request_id`.
