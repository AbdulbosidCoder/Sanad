"""Business modules. ``ALL_MODULES`` is the single list of what the system is made of."""

from app.core.modules import ModuleInfo
from app.modules.analytics.module import MODULE as analytics
from app.modules.audit.module import MODULE as audit
from app.modules.cart.module import MODULE as cart
from app.modules.catalog.module import MODULE as catalog
from app.modules.engagement.module import MODULE as engagement
from app.modules.i18n.module import MODULE as i18n
from app.modules.identity.module import MODULE as identity
from app.modules.inventory.module import MODULE as inventory
from app.modules.media.module import MODULE as media
from app.modules.notifications.module import MODULE as notifications
from app.modules.orders.module import MODULE as orders
from app.modules.payments.module import MODULE as payments
from app.modules.platform.module import MODULE as platform
from app.modules.recommendations.module import MODULE as recommendations
from app.modules.reviews.module import MODULE as reviews
from app.modules.search.module import MODULE as search
from app.modules.stores.module import MODULE as stores
from app.modules.support.module import MODULE as support

ALL_MODULES: tuple[ModuleInfo, ...] = (
    identity,
    stores,
    media,
    catalog,
    i18n,
    inventory,
    search,
    cart,
    payments,
    orders,
    reviews,
    engagement,
    recommendations,
    analytics,
    support,
    notifications,
    audit,
    platform,
)
