# Модуль `notifications`

Уведомления: in-app, email, позже SMS и push.

## Связи

**Зависит от (вызывает их `service.py`):**
- `identity`

**Используется модулями:**
- —

**Публикует события:**
- —

**Слушает события:**
- `OrderPlaced`
- `PaymentSucceeded`
- `SellerOrderStatusChanged`
- `StockLow`
- `TicketReplied`
- `StoreApproved`

**Таблицы:** `notifications`, `notification_preferences`

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и его связей (видно в `GET /api/v1/system/modules`) |
| `api.py` | HTTP-эндпоинты: принимают запрос, проверяют права, вызывают `service.py` |
| `service.py` | Бизнес-логика. Единственная точка входа для других модулей |
| `events.py` | События, которые модуль публикует и на которые подписан |
| `models.py`, `repository.py`, `schemas.py` | Появятся вместе с функциональностью |

## Где искать баг

Симптомы, которые обычно ведут сюда: не пришло письмо или уведомление.

В ошибке API и в логах ищите `"module": "notifications"` и `request_id`.
