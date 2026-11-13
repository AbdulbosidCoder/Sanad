# 3. Модель данных (ER)

Общие соглашения:
- Первичные ключи `UUID` (v7, сортируемые по времени): безопасно отдавать наружу, не раскрывают объёмы.
- У всех таблиц `created_at`, `updated_at`; у удаляемых пользователем сущностей — `deleted_at` (мягкое удаление).
- Деньги: `NUMERIC(14,2)` + `currency` (ISO 4217, по умолчанию `UZS`). Никаких float.
- Все таблицы с данными продавца содержат `store_id`, и все запросы продавца фильтруются по нему на уровне репозитория (см. раздел безопасности, там же про PostgreSQL RLS как второй рубеж).

## 3.1 Identity и магазины

```mermaid
erDiagram
    USER ||--o{ USER_ROLE : has
    ROLE ||--o{ USER_ROLE : assigned
    ROLE ||--o{ ROLE_PERMISSION : grants
    PERMISSION ||--o{ ROLE_PERMISSION : in
    USER ||--o{ SESSION : opens
    SESSION ||--o{ REFRESH_TOKEN : rotates
    USER ||--o{ ADDRESS : owns
    USER ||--o{ STORE_MEMBERSHIP : member
    STORE ||--o{ STORE_MEMBERSHIP : staff
    USER ||--o{ SELLER_APPLICATION : submits
    SELLER_APPLICATION |o--o| STORE : creates

    USER {
        uuid id PK
        string email UK
        string phone UK
        string password_hash
        string full_name
        string locale "uz | ru | en"
        string status "active | blocked | pending"
        bool email_verified
        timestamptz last_login_at
    }
    ROLE {
        uuid id PK
        string code UK "customer, seller_owner, admin..."
        string scope "platform | store"
    }
    PERMISSION {
        uuid id PK
        string code UK "orders.refund, products.write..."
    }
    USER_ROLE {
        uuid user_id FK
        uuid role_id FK
    }
    ROLE_PERMISSION {
        uuid role_id FK
        uuid permission_id FK
    }
    SESSION {
        uuid id PK
        uuid user_id FK
        string device_info
        inet ip
        timestamptz expires_at
        timestamptz revoked_at
    }
    REFRESH_TOKEN {
        uuid id PK
        uuid session_id FK
        string token_hash
        uuid replaced_by
        timestamptz used_at
    }
    STORE {
        uuid id PK
        uuid owner_id FK
        string slug UK
        string name
        string status "pending | active | suspended"
        numeric commission_rate
    }
    STORE_MEMBERSHIP {
        uuid store_id FK
        uuid user_id FK
        string store_role "owner | manager | staff"
    }
    SELLER_APPLICATION {
        uuid id PK
        uuid user_id FK
        string status "submitted | approved | rejected"
        jsonb documents
        uuid reviewed_by FK
    }
    ADDRESS {
        uuid id PK
        uuid user_id FK
        string region
        string city
        string line1
        string phone
        bool is_default
    }
```

## 3.2 Каталог, переводы, склад

```mermaid
erDiagram
    STORE ||--o{ PRODUCT : sells
    CATEGORY ||--o{ PRODUCT : classifies
    CATEGORY ||--o{ CATEGORY : parent
    BRAND ||--o{ PRODUCT : brands
    PRODUCT ||--o{ PRODUCT_TRANSLATION : translated
    PRODUCT ||--o{ PRODUCT_IMAGE : shows
    PRODUCT ||--|{ PRODUCT_VARIANT : has
    PRODUCT_VARIANT ||--|| INVENTORY : stock
    PRODUCT_VARIANT ||--o{ STOCK_RESERVATION : reserved
    PRODUCT_VARIANT ||--o{ STOCK_MOVEMENT : moves
    CATEGORY ||--o{ CATEGORY_TRANSLATION : translated

    PRODUCT {
        uuid id PK
        uuid store_id FK
        uuid category_id FK
        uuid brand_id FK
        string slug
        string source_locale "язык оригинала"
        string status "draft | active | archived"
        numeric tax_rate
        numeric rating_avg
        int rating_count
        tsvector search_vector
    }
    PRODUCT_TRANSLATION {
        uuid product_id FK
        string locale
        string title
        text description
        jsonb specifications
        string origin "original | machine | manual"
        string source_hash "хэш оригинала на момент перевода"
    }
    PRODUCT_VARIANT {
        uuid id PK
        uuid product_id FK
        string sku UK
        jsonb attributes "size, color"
        numeric price
        numeric compare_at_price
        string unit "шт, кг, м"
        bool is_active
    }
    INVENTORY {
        uuid variant_id PK
        int on_hand
        int reserved
        int low_stock_threshold
        int version "оптимистичная блокировка"
    }
    STOCK_RESERVATION {
        uuid id PK
        uuid variant_id FK
        uuid order_id FK
        int quantity
        timestamptz expires_at
    }
    STOCK_MOVEMENT {
        uuid id PK
        uuid variant_id FK
        int delta
        string reason "sale | return | manual | cancel"
        uuid actor_id
    }
    PRODUCT_IMAGE {
        uuid id PK
        uuid product_id FK
        string storage_key
        int position
    }
    CATEGORY {
        uuid id PK
        uuid parent_id FK
        string slug UK
    }
    CATEGORY_TRANSLATION {
        uuid category_id FK
        string locale
        string name
    }
    BRAND {
        uuid id PK
        string name
        string slug UK
    }
```

**Скидки:** в V1 скидка задаётся через `compare_at_price` на варианте (старая цена) плюс таблица `DISCOUNT` (процент/сумма, период действия, область: товар/магазин). Промокоды — V1.1.

## 3.3 Корзина, заказы, платежи

```mermaid
erDiagram
    USER ||--o| CART : owns
    CART ||--o{ CART_ITEM : contains
    PRODUCT_VARIANT ||--o{ CART_ITEM : refers
    USER ||--o{ ORDER : places
    ORDER ||--|{ SELLER_ORDER : splits
    STORE ||--o{ SELLER_ORDER : fulfils
    SELLER_ORDER ||--|{ ORDER_ITEM : contains
    SELLER_ORDER ||--o{ ORDER_STATUS_HISTORY : tracks
    ORDER ||--o{ PAYMENT : paid_by
    PAYMENT ||--o{ PAYMENT_ATTEMPT : tries
    PAYMENT ||--o{ REFUND : refunded
    SELLER_ORDER ||--o{ RETURN_REQUEST : returns
    RETURN_REQUEST |o--o| REFUND : triggers
    PAYMENT ||--o{ LEDGER_ENTRY : posts

    CART {
        uuid id PK
        uuid user_id FK "null для гостя"
        string guest_token
    }
    CART_ITEM {
        uuid cart_id FK
        uuid variant_id FK
        int quantity
    }
    ORDER {
        uuid id PK
        string number UK "человекочитаемый"
        uuid user_id FK
        jsonb shipping_address "снимок"
        numeric total
        string currency
        string status "placed | partially_fulfilled | completed | cancelled"
        string payment_status "unpaid | pending | paid | partially_refunded | refunded | failed"
        string idempotency_key UK
    }
    SELLER_ORDER {
        uuid id PK
        uuid order_id FK
        uuid store_id FK
        numeric subtotal
        numeric commission
        string status "new | confirmed | shipped | delivered | cancelled | returned"
        string tracking_number
    }
    ORDER_ITEM {
        uuid id PK
        uuid seller_order_id FK
        uuid variant_id FK
        string title_snapshot
        numeric unit_price
        numeric tax_amount
        int quantity
    }
    ORDER_STATUS_HISTORY {
        uuid id PK
        uuid seller_order_id FK
        string from_status
        string to_status
        uuid actor_id
    }
    PAYMENT {
        uuid id PK
        uuid order_id FK
        string provider "fake | uzcard | humo | visa"
        string provider_payment_id
        numeric amount
        string status "created | pending | succeeded | failed | cancelled"
        bool is_test "true для FakeProvider"
    }
    PAYMENT_ATTEMPT {
        uuid id PK
        uuid payment_id FK
        string result
        jsonb provider_response "без данных карты"
    }
    REFUND {
        uuid id PK
        uuid payment_id FK
        uuid seller_order_id FK
        numeric amount
        string status "requested | approved | processing | completed | failed"
        uuid approved_by FK
    }
    RETURN_REQUEST {
        uuid id PK
        uuid seller_order_id FK
        string reason
        string status
    }
    LEDGER_ENTRY {
        uuid id PK
        uuid payment_id FK
        uuid store_id FK
        string type "sale | commission | refund | payout"
        numeric amount
    }
```

**Ключевые правила:**
- Один checkout → один `ORDER` (родитель) → по одному `SELLER_ORDER` на каждый магазин.
- `ORDER.status` и `ORDER.payment_status` независимы; статус каждого `SELLER_ORDER` тоже независим.
- Цены, название товара и адрес **копируются** в заказ (снимок), чтобы изменения каталога не меняли историю.
- Списание остатков: `UPDATE inventory SET reserved = reserved + :q WHERE variant_id = :id AND on_hand - reserved >= :q` в транзакции — атомарно, без гонок. Резерв истекает, если оплата не прошла за N минут.
- `LEDGER_ENTRY` — двойная запись для финансов: продажа, комиссия платформы, возврат, выплата. Только вставка, никаких UPDATE/DELETE.

## 3.4 Вовлечённость, поддержка, аудит

```mermaid
erDiagram
    USER ||--o{ REVIEW : writes
    PRODUCT ||--o{ REVIEW : has
    ORDER_ITEM ||--o| REVIEW : verifies
    USER ||--o{ FAVORITE : saves
    USER ||--o{ SEARCH_HISTORY : searches
    USER ||--o{ PRODUCT_VIEW : views
    USER ||--o{ RECOMMENDATION : receives
    USER ||--o{ SUPPORT_TICKET : opens
    SUPPORT_TICKET ||--o{ SUPPORT_MESSAGE : thread
    USER ||--o{ NOTIFICATION : gets
    USER ||--o{ AUDIT_LOG : acts

    REVIEW {
        uuid id PK
        uuid product_id FK
        uuid user_id FK
        uuid order_item_id FK "только после покупки"
        int rating
        text body
        string status "published | hidden"
    }
    FAVORITE {
        uuid user_id FK
        uuid product_id FK
    }
    SEARCH_HISTORY {
        uuid id PK
        uuid user_id FK
        string query
        int results_count
    }
    PRODUCT_VIEW {
        uuid id PK
        uuid product_id FK
        uuid user_id FK
        string session_id
        string source "search | home | recommendation"
    }
    RECOMMENDATION {
        uuid user_id FK
        uuid product_id FK
        float score
        string reason
    }
    SUPPORT_TICKET {
        uuid id PK
        uuid user_id FK
        uuid order_id FK
        uuid assignee_id FK
        string category
        string priority
        string status "open | pending | resolved | closed"
    }
    SUPPORT_MESSAGE {
        uuid id PK
        uuid ticket_id FK
        uuid author_id FK
        text body
        bool internal_note
    }
    NOTIFICATION {
        uuid id PK
        uuid user_id FK
        string type
        jsonb payload
        timestamptz read_at
    }
    AUDIT_LOG {
        bigint id PK
        uuid actor_id FK
        string action "refund.approve, user.block..."
        string target_type
        uuid target_id
        jsonb before
        jsonb after
        inet ip
        string request_id
        string prev_hash "цепочка хэшей"
    }
```

- `PRODUCT_VIEW` и `SEARCH_HISTORY` — высоконагруженные таблицы: партиционирование по месяцу, хранение сырых данных 90 дней, дальше только агрегаты.
- `AUDIT_LOG` — только вставка (права БД на UPDATE/DELETE отозваны), цепочка хэшей для обнаружения подмены.
- Аналитика продавца считается не из сырых таблиц на лету, а из ночных/почасовых агрегатов `SELLER_DAILY_STATS`, `PRODUCT_DAILY_STATS` (просмотры, показы в поиске, добавления в корзину, заказы, выручка).
