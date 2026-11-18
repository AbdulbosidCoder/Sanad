# Модуль `notifications`

Уведомления в приложении («колокольчик») и по email. SMS и push — позже.

## Связи

**Зависит от:** `identity` (email, язык пользователя), `stores` (кому из сотрудников магазина писать)

**Слушает события:**

| Событие | Кому | kind |
|---|---|---|
| `OrderPlaced` | покупателю | `order_placed` (только в приложении) |
| `OrderPaid` | покупателю + сотрудникам с `orders.seller_manage` каждого магазина | `order_paid`, `store_new_order` |
| `OrderCancelled` | покупателю | `order_cancelled` |
| `SellerOrderStatusChanged` | покупателю (confirmed/shipped/delivered/cancelled/returned) | `order_status` |
| `RefundCompleted` | покупателю | `refund_completed` |
| `StockLow` | сотрудникам с `inventory.write` | `stock_low` (только в приложении) |
| `StoreApproved` / `SellerApplicationRejected` | заявителю | `store_approved`, `application_rejected` |
| `StoreSuspended` | сотрудникам с `store.settings_manage` | `store_suspended` |

**Таблицы:** `notifications`, `notification_preferences`, `email_outbox`

## Как это работает

1. Модуль-источник публикует событие в своей транзакции.
2. Обработчик пишет уведомление на языке получателя (`users.locale`, тексты в `templates.py`)
   и, если этот kind идёт по почте и почта не выключена, — письмо в `email_outbox`.
3. Воркер `notifications.send_emails` (каждую минуту) отправляет письма: 5 попыток, потом `failed`.

Почтовый сервер не работает → заказ всё равно проходит, письмо ждёт в очереди.

`EMAIL_BACKEND=console` (по умолчанию) — письма только пишутся в лог. Для настоящей почты:
`EMAIL_BACKEND=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`
(пароль только в своём `.env`).

## API

| Метод | Путь | Что |
|---|---|---|
| GET | `/me/notifications?unread_only=` | Входящие, новые сверху |
| GET | `/me/notifications/unread-count` | Цифра на колокольчике |
| POST | `/me/notifications/{id}/read`, `/me/notifications/read-all` | Прочитано |
| GET / PATCH | `/me/notification-preferences` | `email_enabled`, `muted_kinds` |

## Где искать ошибку

- Нет уведомления: подписан ли обработчик (`setup` в `module.py`), не в `muted_kinds` ли kind,
  активен ли пользователь.
- Не пришло письмо: `select status, attempts, last_error from email_outbox order by created_at desc`.
