# Модуль `support`

Обращения в поддержку: переписка покупателя с сотрудниками, внутренние заметки, очередь и назначение.

## Связи

**Зависит от:** `identity` (имя и email покупателя для сотрудника), `orders` (номер заказа и что он
принадлежит покупателю), `audit` (переназначение)

**Публикует:** `TicketCreated`, `TicketReplied` (notifications шлёт покупателю «Ответ поддержки»)

**Таблицы:** `support_tickets`, `support_messages`

## Статусы

`open` (ждёт поддержку) → `answered` (ждёт покупателя) → `resolved` → `closed`.
Новое сообщение покупателя возвращает тикет в `open` (и из `resolved`). Закрытый тикет не продолжается.
Категории `payment` и `return` сразу получают приоритет `high`.

## Кто что видит

| Кто | Видит |
|---|---|
| Покупатель | Только свои тикеты, без внутренних заметок |
| `support.tickets_handle` (агент) | Назначенные ему и неназначенные; кто первым ответил — тому и назначен |
| `support.tickets_read` / `support.tickets_assign` (лид, админ) | Все; `tickets_assign` переназначает (в аудит) |

Очередь сортируется по `last_activity_at` — дольше всех ждущий сверху.

## API

| Метод | Путь | Что |
|---|---|---|
| POST / GET | `/support/tickets` | Создать / мои тикеты |
| GET | `/support/tickets/{id}` | Тикет с перепиской |
| POST | `/support/tickets/{id}/messages`, `/close` | Ответить / закрыть |
| GET | `/admin/support/tickets?status=&mine=&unassigned=` | Очередь |
| GET / PATCH | `/admin/support/tickets/{id}` | Тикет, статус и приоритет |
| POST | `/admin/support/tickets/{id}/messages` | Ответ или заметка (`internal: true`) |
| POST | `/admin/support/tickets/{id}/assign` | Назначить (`support.tickets_assign`) |
