# 6. Основные сценарии

## 6.1 Checkout с несколькими продавцами

```mermaid
sequenceDiagram
    autonumber
    actor C as Покупатель
    participant API as API /checkout
    participant CART as cart
    participant INV as inventory
    participant ORD as orders
    participant PAY as payments
    participant P as FakeProvider
    participant W as Worker

    C->>API: POST /checkout (Idempotency-Key)
    API->>CART: получить корзину
    API->>ORD: создать Order + SellerOrder на каждый магазин
    ORD->>INV: резерв остатков (атомарный UPDATE, одна транзакция)
    alt не хватает остатков
        INV-->>API: 409 OUT_OF_STOCK (какие позиции)
        API-->>C: показать, что изменилось
    else всё зарезервировано
        ORD->>PAY: create_payment(order.total)
        PAY->>P: create_payment
        P-->>PAY: pending + redirect / форма
        API-->>C: 201 Order (payment_status = pending)
        C->>P: подтверждает оплату (в Fake — выбирает исход)
        P-->>API: webhook payment.succeeded (подпись)
        API->>W: в очередь (дедупликация event_id)
        W->>PAY: Payment = succeeded
        W->>ORD: событие PaymentSucceeded → Order.payment_status = paid
        W->>INV: резерв → списание (on_hand -= q)
        W-->>C: уведомление «Заказ оплачен»
        W-->>W: уведомления каждому продавцу о его SellerOrder
    end
    Note over INV,W: Если оплата не пришла за 15 мин — резерв снимается, заказ отменяется
```

## 6.2 Жизненный цикл заказа продавца

```mermaid
stateDiagram-v2
    [*] --> new: оплачен
    new --> confirmed: продавец принял
    new --> cancelled: продавец/покупатель отменил
    confirmed --> shipped: отправлен (трек-номер)
    confirmed --> cancelled
    shipped --> delivered: доставлен
    delivered --> return_requested: запрос возврата (до N дней)
    return_requested --> returned: возврат принят
    return_requested --> delivered: отказ
    cancelled --> [*]: возврат денег за этот SellerOrder
    returned --> [*]: возврат денег + остатки назад
    delivered --> [*]
```

Родительский `Order.status` вычисляется из статусов всех `SellerOrder` (`completed`, если все доставлены/закрыты; `partially_fulfilled` и т. д.). Платёжный статус меняется отдельно: частичный возврат одного продавца даёт `payment_status = partially_refunded`.

## 6.3 Создание товара продавцом и автоперевод

```mermaid
sequenceDiagram
    actor S as Продавец
    participant API as /seller/products
    participant MEDIA as media
    participant CAT as catalog
    participant W as Worker
    participant TR as Translator
    participant SRCH as search

    S->>API: запросить presigned URL для фото
    API->>MEDIA: проверить тип, размер, квоту
    MEDIA-->>S: presigned PUT URL
    S->>MEDIA: загрузка в S3 напрямую
    S->>API: POST товар (язык оригинала = ru)
    API->>CAT: сохранить Product + ProductTranslation(ru, original)
    CAT-->>W: ProductCreated (через outbox)
    W->>MEDIA: проверка файла (magic bytes), ресайз, WebP, удаление EXIF
    W->>TR: ru → uz, ru → en
    TR-->>W: переводы
    W->>CAT: ProductTranslation(uz/en, origin = machine)
    W->>SRCH: обновить индекс на 3 языках
    S->>API: (опционально) правка перевода en → origin = manual
```

## 6.4 Возврат денег

```mermaid
sequenceDiagram
    actor C as Покупатель
    actor SL as Продавец / Поддержка
    actor F as Финансы
    participant ORD as orders
    participant PAY as payments
    participant AUD as audit

    C->>ORD: запрос возврата по позиции
    SL->>ORD: одобрить возврат товара
    ORD->>PAY: Refund(requested)
    F->>PAY: одобрить (не тот же человек, что инициировал)
    PAY->>AUD: refund.approve (до/после, IP, request_id)
    PAY->>PAY: provider.refund() (Idempotency-Key)
    PAY-->>ORD: RefundCompleted
    ORD->>ORD: SellerOrder = returned, остатки +q, LedgerEntry(refund)
```

## 6.5 Регистрация продавца

Покупатель → «Стать продавцом» → заявка (название магазина, контакты, документы) → админ проверяет → одобрено: создаётся `Store` (status = active) и `StoreMembership(owner)`, пользователь получает роль `seller_owner` в этом магазине → доступ к панели продавца. Все шаги одобрения пишутся в аудит.

## 6.6 Рекомендации (V1, базовые)

- **Новый пользователь** (нет истории): «Хиты недели» = топ по продажам за 7 дней, отдельно по категориям.
- **С историей:** ночная задача считает оценку товаров: похожие на просмотренные/избранные/купленные (та же категория и бренд, близкая цена) + «покупают вместе» (совместные покупки). Результат — `Recommendation` в БД и кэш в Redis.
- **Тренды:** рост просмотров и добавлений в корзину за 24–72 часа.
- Интерфейс модуля позволит в будущем заменить алгоритм на ML-модель без изменения API `/home`.
