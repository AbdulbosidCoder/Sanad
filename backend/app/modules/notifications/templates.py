"""Texts of notifications in uz / ru / en. ``{name}`` fields come from the event."""

from typing import NamedTuple


class Text(NamedTuple):
    title: str
    body: str


T = dict[str, Text]

TEMPLATES: dict[str, T] = {
    "order_placed": {
        "uz": Text("{number} buyurtma rasmiylashtirildi", "Buyurtmani 30 daqiqa ichida to'lang."),
        "ru": Text("Заказ {number} оформлен", "Оплатите его в течение 30 минут."),
        "en": Text("Order {number} placed", "Please pay for it within 30 minutes."),
    },
    "order_paid": {
        "uz": Text("{number} buyurtma to'landi", "Rahmat! Sotuvchilar buyurtmani tayyorlamoqda."),
        "ru": Text("Заказ {number} оплачен", "Спасибо! Продавцы уже собирают заказ."),
        "en": Text("Order {number} is paid", "Thank you! The sellers are preparing it."),
    },
    "order_cancelled": {
        "uz": Text("{number} buyurtma bekor qilindi", "{reason}"),
        "ru": Text("Заказ {number} отменён", "{reason}"),
        "en": Text("Order {number} cancelled", "{reason}"),
    },
    "order_status": {
        "uz": Text("{number}: {status}", "Buyurtma holati o'zgardi."),
        "ru": Text("{number}: {status}", "Статус заказа изменился."),
        "en": Text("{number}: {status}", "Your order status changed."),
    },
    "refund_completed": {
        "uz": Text("Pul qaytarildi", "{amount} so'm kartangizga qaytarildi."),
        "ru": Text("Деньги возвращены", "{amount} сум вернулись на вашу карту."),
        "en": Text("Refund completed", "{amount} UZS returned to your card."),
    },
    "store_new_order": {
        "uz": Text("Yangi buyurtma {number}", "To'langan buyurtma. Tasdiqlang va jo'nating."),
        "ru": Text("Новый заказ {number}", "Заказ оплачен. Подтвердите и отправьте."),
        "en": Text("New order {number}", "The order is paid. Confirm and ship it."),
    },
    "stock_low": {
        "uz": Text("Tovar tugayapti: {sku}", "{title}: {available} dona qoldi."),
        "ru": Text("Заканчивается товар: {sku}", "{title}: осталось {available} шт."),
        "en": Text("Running low: {sku}", "{title}: {available} left."),
    },
    "store_approved": {
        "uz": Text("«{name}» do'koni ochildi", "Endi tovar qo'shishingiz mumkin."),
        "ru": Text("Магазин «{name}» открыт", "Теперь можно добавлять товары."),
        "en": Text("Store “{name}” is open", "You can add products now."),
    },
    "application_rejected": {
        "uz": Text("«{name}» arizasi rad etildi", "{note}"),
        "ru": Text("Заявка «{name}» отклонена", "{note}"),
        "en": Text("Application “{name}” rejected", "{note}"),
    },
    "store_suspended": {
        "uz": Text("«{name}» do'koni to'xtatildi", "{reason}"),
        "ru": Text("Магазин «{name}» приостановлен", "{reason}"),
        "en": Text("Store “{name}” suspended", "{reason}"),
    },
    "ticket_replied": {
        "uz": Text("Qo'llab-quvvatlash javob berdi", "{subject}"),
        "ru": Text("Ответ поддержки", "{subject}"),
        "en": Text("Support replied", "{subject}"),
    },
}

STATUS_NAMES: dict[str, dict[str, str]] = {
    "confirmed": {"uz": "tasdiqlandi", "ru": "подтверждён", "en": "confirmed"},
    "shipped": {"uz": "jo'natildi", "ru": "отправлен", "en": "shipped"},
    "delivered": {"uz": "yetkazildi", "ru": "доставлен", "en": "delivered"},
    "cancelled": {
        "uz": "bekor qilindi",
        "ru": "отменён продавцом",
        "en": "cancelled by the seller",
    },
    "returned": {"uz": "qaytarildi", "ru": "возвращён", "en": "returned"},
}

# Kinds that also go by e-mail (the rest stay in the app only).
EMAIL_KINDS = frozenset(
    {
        "order_paid",
        "order_cancelled",
        "order_status",
        "refund_completed",
        "store_new_order",
        "store_approved",
        "application_rejected",
        "store_suspended",
        "ticket_replied",
    }
)


class _Safe(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def render(kind: str, locale: str, params: dict[str, str]) -> Text:
    by_locale = TEMPLATES[kind]
    t = by_locale.get(locale) or by_locale["ru"]
    values = _Safe(params)
    return Text(t.title.format_map(values)[:200], t.body.format_map(values))
