"""Demo data for local testing: ``python -m app.seed`` (or ``make seed``).

Creates up to 10 records of each kind through the modules' own services, so the data
obeys the same rules as data made through the API:

- 10 users: super admin, admin, support lead, 3 sellers, 4 buyers (one password for all);
- 5 seller applications: 3 approved (-> 3 stores), 1 waiting, 1 rejected;
- 10 categories (tree), 10 brands;
- 10 products with 2-5 variants, 7 seller photos (one per side), buyer photos, stock
  (some variants low or sold out, to test low-stock);
- delivery addresses for the buyers.

Safe to run again: if the demo admin already exists, nothing is changed.
Refuses to run outside dev/test, because every demo account shares a known password.
"""

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.models import uuid7
from app.modules.catalog import service as catalog
from app.modules.catalog.schemas import BrandIn, CategoryIn, ImageIn, Names, ProductIn, VariantIn
from app.modules.identity import service as identity
from app.modules.identity.schemas import AddressIn, RegisterIn
from app.modules.inventory import service as inventory
from app.modules.inventory.schemas import StockUpdate
from app.modules.stores import service as stores
from app.modules.stores.schemas import ApplicationIn
from app.modules.stores.service import StoreAccess

PASSWORD = "Demo12345!"  # noqa: S105 - shared demo password, dev/test only
DOMAIN = "example.com"  # reserved for examples: mail to it never reaches anyone
MARKER = f"admin@{DOMAIN}"

# email local part, full name, phone, platform role (None = buyer only)
USERS: list[tuple[str, str, str, str | None]] = [
    ("admin", "Super Admin", "+998900000001", "super_admin"),
    ("moderator", "Dilnoza Karimova", "+998900000002", "admin"),
    ("support", "Bekzod Toshmatov", "+998900000003", "support_lead"),
    ("seller1", "Jasur Aliyev", "+998900000004", None),
    ("seller2", "Madina Yusupova", "+998900000005", None),
    ("seller3", "Otabek Rahimov", "+998900000006", None),
    ("buyer1", "Aziza Nurmatova", "+998900000007", None),
    ("buyer2", "Sardor Ergashev", "+998900000008", None),
    ("buyer3", "Kamola Saidova", "+998900000009", None),
    ("buyer4", "Timur Qodirov", "+998900000010", None),
]

# applicant, store name, description, decision
APPLICATIONS = [
    ("seller1", "Sneaker Lab", "Оригинальные кроссовки Nike и Jordan", "approve"),
    ("seller2", "Urban Step", "Кеды и кроссовки на каждый день", "approve"),
    ("seller3", "Outdoor Uz", "Одежда для города и путешествий", "approve"),
    ("buyer4", "Timur Shoes", "Хочу продавать обувь", "pending"),
    ("buyer3", "Kamola Bags", "Сумки ручной работы", "reject"),
]

# slug, parent slug, uz, ru, en
CATEGORIES = [
    ("shoes", None, "Poyabzal", "Обувь", "Shoes"),
    ("sneakers", "shoes", "Krossovkalar", "Кроссовки", "Sneakers"),
    ("canvas-shoes", "shoes", "Kedlar", "Кеды", "Canvas shoes"),
    ("boots", "shoes", "Botinkalar", "Ботинки", "Boots"),
    ("clothing", None, "Kiyim", "Одежда", "Clothing"),
    ("hoodies", "clothing", "Xudilar", "Худи", "Hoodies"),
    ("t-shirts", "clothing", "Futbolkalar", "Футболки", "T-shirts"),
    ("jackets", "clothing", "Kurtkalar", "Куртки", "Jackets"),
    ("accessories", None, "Aksessuarlar", "Аксессуары", "Accessories"),
    ("bags", "accessories", "Sumkalar", "Сумки", "Bags"),
]

BRANDS = [
    ("nike", "Nike"),
    ("adidas", "Adidas"),
    ("jordan", "Jordan"),
    ("new-balance", "New Balance"),
    ("asics", "Asics"),
    ("converse", "Converse"),
    ("vans", "Vans"),
    ("puma", "Puma"),
    ("the-north-face", "The North Face"),
    ("reebok", "Reebok"),
]

SHOE_SIZES = ["40", "41", "42", "43", "44"]
CLOTHES_SIZES = ["S", "M", "L", "XL"]


@dataclass
class DemoProduct:
    store: str  # seller login
    category: str
    brand: str
    title: str
    description: str
    color: str
    price: int
    old_price: int | None
    sizes: list[str]
    stock: list[int]  # per size; 0 = sold out, small = low stock


PRODUCTS = [
    DemoProduct(
        "seller1",
        "sneakers",
        "nike",
        "Nike Air Max 90",
        "Классика 1990 года: видимая воздушная подушка Air, кожа и замша.",
        "white",
        1_450_000,
        1_690_000,
        SHOE_SIZES,
        [6, 12, 9, 3, 0],
    ),
    DemoProduct(
        "seller1",
        "sneakers",
        "nike",
        "Nike Air Force 1 '07",
        "Белые кожаные кроссовки на каждый день.",
        "white",
        1_290_000,
        None,
        SHOE_SIZES,
        [10, 15, 14, 8, 4],
    ),
    DemoProduct(
        "seller1",
        "sneakers",
        "jordan",
        "Air Jordan 1 Mid",
        "Баскетбольная классика в повседневном исполнении.",
        "black-red",
        1_890_000,
        2_100_000,
        SHOE_SIZES[1:],
        [2, 5, 1, 0],
    ),
    DemoProduct(
        "seller1",
        "sneakers",
        "adidas",
        "Adidas Samba OG",
        "Кожаный верх, замшевые накладки, каучуковая подошва.",
        "white-black",
        1_190_000,
        None,
        SHOE_SIZES,
        [7, 9, 11, 6, 2],
    ),
    DemoProduct(
        "seller2",
        "sneakers",
        "new-balance",
        "New Balance 550",
        "Ретро-силуэт из 80-х, кожаный верх.",
        "white-green",
        1_350_000,
        None,
        SHOE_SIZES,
        [4, 6, 8, 5, 3],
    ),
    DemoProduct(
        "seller2",
        "sneakers",
        "asics",
        "Asics Gel-Kayano 14",
        "Беговой силуэт 2008 года с амортизацией GEL.",
        "silver",
        1_590_000,
        1_790_000,
        SHOE_SIZES[:4],
        [3, 1, 2, 0],
    ),
    DemoProduct(
        "seller2",
        "canvas-shoes",
        "converse",
        "Converse Chuck 70 Hi",
        "Высокие кеды из плотного канваса.",
        "black",
        890_000,
        None,
        SHOE_SIZES,
        [12, 10, 9, 7, 5],
    ),
    DemoProduct(
        "seller2",
        "canvas-shoes",
        "vans",
        "Vans Old Skool",
        "Скейтерские кеды с фирменной полосой.",
        "black-white",
        790_000,
        920_000,
        SHOE_SIZES,
        [8, 8, 6, 4, 1],
    ),
    DemoProduct(
        "seller3",
        "jackets",
        "the-north-face",
        "The North Face 1996 Nuptse",
        "Пуховик с наполнителем 700 fill power.",
        "black",
        3_200_000,
        None,
        CLOTHES_SIZES,
        [2, 4, 3, 1],
    ),
    DemoProduct(
        "seller3",
        "hoodies",
        "puma",
        "Puma Essentials Big Logo Hoodie",
        "Мягкий флис, капюшон на шнурке.",
        "grey",
        490_000,
        590_000,
        CLOTHES_SIZES,
        [15, 20, 12, 6],
    ),
]

SIDES = ["left", "right", "top", "sole", "inside", "back", "label"]


def _photo(title: str, side: str, by_buyer: bool = False) -> str:
    """Placeholder image with the product and side written on it (no external photos)."""
    bg, fg = ("e8f3ee", "0f3d2e") if by_buyer else ("0f3d2e", "ffffff")
    label = f"{title} | {'buyer photo' if by_buyer else side}"
    return f"https://placehold.co/800x800/{bg}/{fg}/png?text={quote(label)}"


def _principal(user_id: uuid.UUID) -> Principal:
    return Principal(user_id=user_id, session_id=uuid7())


async def _seed(db: AsyncSession) -> None:
    await identity.sync_rbac(db)
    await db.commit()

    users: dict[str, uuid.UUID] = {}
    for login, name, phone, role in USERS:
        users[login] = await identity.create_user(
            db,
            RegisterIn(
                email=f"{login}@{DOMAIN}",
                phone=phone,
                password=PASSWORD,
                full_name=name,
                locale="ru",
            ),
        )
        await db.commit()
        if role:
            await identity.grant_role(db, users[login], role)
    admin = _principal(users["admin"])
    print(f"users: {len(users)}")

    store_ids: dict[str, uuid.UUID] = {}
    for login, store_name, description, decision in APPLICATIONS:
        application = await stores.apply(
            db,
            _principal(users[login]),
            ApplicationIn(
                store_name=store_name,
                description=description,
                phone=dict((u[0], u[2]) for u in USERS)[login],
            ),
        )
        if decision == "approve":
            done = await stores.approve(db, admin, application.id, "Документы в порядке")
            if done.store_id is None:
                raise RuntimeError("approval did not create a store")
            store_ids[login] = done.store_id
        elif decision == "reject":
            await stores.reject(db, admin, application.id, "Не хватает документов")
    print(f"seller applications: {len(APPLICATIONS)}, stores: {len(store_ids)}")

    category_ids: dict[str, uuid.UUID] = {}
    for position, (slug, parent, uz, ru, en) in enumerate(CATEGORIES):
        created = await catalog.create_category(
            db,
            CategoryIn(
                slug=slug,
                names=Names(uz=uz, ru=ru, en=en),
                parent_id=category_ids.get(parent) if parent else None,
                position=position,
            ),
        )
        category_ids[slug] = created.id
    brand_ids: dict[str, uuid.UUID] = {}
    for slug, name in BRANDS:
        brand_ids[slug] = (await catalog.create_brand(db, BrandIn(slug=slug, name=name))).id
    print(f"categories: {len(category_ids)}, brands: {len(brand_ids)}")

    buyers = ["buyer1", "buyer2", "buyer3"]
    for n, p in enumerate(PRODUCTS):
        access = StoreAccess(
            store_ids[p.store],
            users[p.store],
            "seller_owner",
            identity.store_role_permissions("seller_owner"),
            True,
        )
        sku_base = f"{p.brand[:3].upper()}-{n + 1:03d}"
        product = await catalog.create_product(
            db,
            access,
            ProductIn(
                title=p.title,
                description=p.description,
                source_locale="ru",
                category_id=category_ids[p.category],
                brand_id=brand_ids[p.brand],
                specifications={"color": p.color, "original": True},
                variants=[
                    VariantIn(
                        sku=f"{sku_base}-{size}",
                        attributes={"size": size, "color": p.color},
                        price=Decimal(p.price),
                        compare_at_price=Decimal(p.old_price) if p.old_price else None,
                        position=i,
                    )
                    for i, size in enumerate(p.sizes)
                ],
            ),
            "ru",
        )
        for position, side in enumerate(SIDES):
            await catalog.add_image(
                db,
                access,
                product.id,
                ImageIn(url=_photo(p.title, side), angle=side, position=position),
            )
        await catalog.publish(db, access, product.id, "ru")
        for variant, count in zip(product.variants, p.stock, strict=True):
            await inventory.set_stock(
                db,
                access.store_id,
                variant.id,
                StockUpdate(on_hand=count, low_stock_threshold=3, note="demo data"),
                actor_id=access.user_id,
                reason="seed",
            )
        await db.commit()
        buyer = buyers[n % len(buyers)]
        photo = await catalog.add_buyer_photo(
            db,
            _principal(users[buyer]),
            product.id,
            ImageIn(url=_photo(p.title, "other", by_buyer=True)),
        )
        if n % 4 != 3:  # every fourth buyer photo stays in the moderation queue
            await catalog.moderate_image(db, admin, photo.id, "approved")
    print(f"products: {len(PRODUCTS)} (7 seller photos each, buyer photos, stock)")

    cities = [
        ("Toshkent", "Toshkent"),
        ("Samarqand", "Samarqand"),
        ("Buxoro", "Buxoro"),
        ("Farg'ona", "Farg'ona"),
    ]
    for i, login in enumerate(["buyer1", "buyer2", "buyer3", "buyer4"]):
        region, city = cities[i]
        name, phone = next((u[1], u[2]) for u in USERS if u[0] == login)
        await identity.create_address(
            db,
            _principal(users[login]),
            AddressIn(
                recipient_name=name,
                phone=phone,
                region=region,
                city=city,
                line1=f"Mustaqillik ko'chasi, {10 + i}",
                is_default=True,
            ),
        )
    print("addresses: 4")


async def run(if_empty: bool) -> int:
    settings = get_settings()
    if settings.app_env not in ("dev", "test"):
        print(f"refusing to seed demo data in APP_ENV={settings.app_env}", file=sys.stderr)
        return 1
    async with get_sessionmaker()() as db:
        if await identity.find_user_id(db, MARKER) is not None:
            print(f"demo data is already there ({MARKER} exists): nothing to do")
            return 0
        await _seed(db)
    print(f"\nDone. Sign in with any {DOMAIN} account, password: {PASSWORD}")
    print(f"  admin:   {MARKER}            (super_admin)")
    print(f"  seller:  seller1@{DOMAIN}          (store Sneaker Lab)")
    print(f"  buyer:   buyer1@{DOMAIN}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description=__doc__.split("\n")[0])
    parser.add_argument(
        "--if-empty", action="store_true", help="kept for scripts; seeding is always idempotent"
    )
    args = parser.parse_args(argv)
    return asyncio.run(run(args.if_empty))


if __name__ == "__main__":
    raise SystemExit(main())
