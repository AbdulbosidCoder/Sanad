# Модуль `orders`

Checkout, родительский заказ и заказы продавцов, статусы, отмены, возвраты товара.

## Связи

**Зависит от:** `cart`, `identity` (адрес), `inventory` (резерв, списание, возврат на склад), `payments`, `stores` (комиссия, доступ продавца), `audit` (позже)
**Слушает:** `PaymentSucceeded` (заказ оплачен, резерв списывается), `PaymentFailed` (резерв снимается, заказ отменён, товары возвращаются в корзину), `RefundCompleted` (статус оплаты, возврат завершён)
**Публикует:** `OrderPlaced`, `OrderPaid`, `OrderCancelled`, `SellerOrderStatusChanged`
**Таблицы:** `orders`, `seller_orders`, `order_items`, `order_status_history`, `return_requests`

## Как проходит покупка

1. `POST /checkout` с заголовком `Idempotency-Key` — в одной транзакции: заказ + по одному `seller_order` на магазин + снимок цен/названий/адреса + резерв остатков на 30 минут + платёж + очистка корзины. Повтор с тем же ключом возвращает тот же заказ.
2. Тестовая оплата: `POST /payments/{id}/confirm`. Успех → `payment_status = paid`, товар списан со склада.
3. Продавец: `new → confirmed → shipped (tracking_number) → delivered`; до отправки можно `cancelled` (оплаченное — деньги возвращаются сразу).
4. Не оплатили за 30 минут — фоновая задача `orders.expire_unpaid` (каждые 5 минут) отменяет заказ и снимает резерв.
5. Возврат: покупатель в течение 14 дней после доставки → продавец `approve` → `receive` (товар вернулся на склад, создан запрос на возврат денег) → финансы одобряют в `/admin/refunds`.

## Эндпоинты

| Метод | Путь | Кто | Что делает |
|---|---|---|---|
| POST | `/checkout/preview` | покупатель | Суммы по магазинам, адрес, способы оплаты |
| POST | `/checkout` | покупатель | Оформить заказ (`Idempotency-Key` обязателен) |
| GET | `/orders`, `/orders/{id}` | покупатель | История и трекинг (части по магазинам, история статусов, платежи) |
| POST | `/orders/{id}/cancel` | покупатель | Отмена, пока ничего не отправлено |
| POST | `/orders/{id}/items/{item_id}/return` | покупатель | Запрос возврата |
| GET | `/orders/returns` | покупатель | Мои возвраты |
| GET | `/seller/orders[/{id}]` | сотрудник магазина | Заказы магазина с адресом доставки |
| PATCH | `/seller/orders/{id}/status` | `orders.seller_manage` | Смена статуса |
| GET/PATCH | `/seller/returns[/{id}]` | `returns.decide` | `approve` / `reject` / `receive` |
| GET | `/admin/orders` | `orders.read` | Все заказы |
| POST | `/admin/seller-orders/{id}/status` | 🔒 `orders.status_override` | Ручная смена статуса сотрудником платформы |

## Где искать баг

Заказ не создаётся: `CART.CART_HAS_PROBLEMS`, `INVENTORY.OUT_OF_STOCK`, `ORDERS.ADDRESS_REQUIRED`. Статус не меняется: `ORDERS.BAD_TRANSITION`, `ORDERS.NOT_PAID`. Ищите `"module": "orders"`; полная история — `history` в ответе заказа.
