
import asyncio
import logging
import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import urljoin

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
#                         LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    force=True,
)



# ============================================================
# 999.MD TELEGRAM MONITOR
# ============================================================
#
# Логика:
#   999.md
#      -> Кишинёв (строго сам город)
#      -> только разрешённые районы
#      -> Частное лицо
#      -> Жилой фонд: Новострой / Вторичный
#      -> категория ремонта
#      -> комнаты
#      -> ценовой диапазон
#      -> Telegram
#
# Отдельно отслеживается изменение цены:
#   100 000 -> отправили
#   110 000 -> не отправляем
#   105 000 -> отправляем повторно
#   104 000 -> отправляем повторно
#
# "Без ремонта, нуждается" считается категорией "Без ремонта".
#
# ВАЖНО:
# Вставь НОВЫЙ токен Telegram. Старый токен из предыдущего
# кода не использовать.
# ============================================================


# ============================================================
#                       НАСТРОЙКИ
# ============================================================

BASE_URL = "https://999.md"

LISTING_URL = (
    "https://999.md/ru/list/real-estate/"
    "apartments-and-rooms?view_type=short"
)

CHECK_INTERVAL = 30
MAX_LISTING_PAGES = 20
DB_FILE = "seen_ads.db"

# Можно оставить значения здесь.
# Лучше хранить токен в переменной окружения BOT_TOKEN.
BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "8665821334:AAHbUjfUz5FzsyUwC0ju2i78gHkiP47Jfac"
)

CHAT_ID = os.getenv(
    "CHAT_ID",
    "832658206"
)

TEST_TELEGRAM = True

# Для обычной работы False.
TEST_SEND_FIRST_AD = False

# Только квартиры с автором "Частное лицо".
REQUIRE_PRIVATE_PERSON = True

# Только сам город Кишинёв, не пригороды.
REQUIRE_CHISINAU = True

# Если True, "Новострой" и "Вторичный" должны быть определены.
REQUIRE_HOUSING_TYPE = True

# [] = 1, 2 и 3 комнаты по таблице.
# [1] = только 1-комнатные и т.д.
ROOMS = []


# ============================================================
#                   РАЗРЕШЁННЫЕ РАЙОНЫ
# ============================================================
#
# НИЧЕГО ДРУГОГО БОТ НЕ ПРИНИМАЕТ.
# ============================================================

ALLOWED_DISTRICTS = (
    "Центр",
    "Ботаника",
    "Рышкановка",
    "Чеканы",
    "Буюканы",
    "Старая Почта",
    "Скулянка",
    "Телецентр",
    "Дурлешты",
)


# ============================================================
#                  ЗАПРЕЩЁННЫЕ НАСЕЛЁННЫЕ ПУНКТЫ
# ============================================================
#
# Они находятся в "Кишинёв мун.", но не являются самим городом.
# Поэтому объявления из них не должны проходить.
# ============================================================

OUTSIDE_CHISINAU = (
    "бачой",
    "băcioi",
    "bacioi",

    "браила",
    "brăila",
    "braila",

    "бубуечь",
    "bubuieci",

    "будешты",
    "budești",
    "budesti",

    "бунэц",
    "bunet",

    "бык",
    "bîc",
    "bic",

    "ваду-луй-водэ",
    "vădul lui vodă",
    "vadul lui voda",

    "ватра",
    "vătra",
    "vatra",

    "вадулянь",
    "vaduleni",

    "гидигич",
    "gîdighici",
    "gidighici",

    "гоян",
    "goian",

    "гратиешты",
    "grătiești",
    "gratiesti",

    "гульбоака",
    "hulboaca",
    "gulboaca",

    "добружа",
    "dobraja",
    "dobruja",

    "думбрава",
    "dumbrava",


    "келтуитор",
    "cheltuitor",

    "кодру",
    "codru",

    "колоница",
    "colonița",
    "colonita",

    "кондрица",
    "condrița",
    "condrita",

    "криково",
    "cricova",

    "крузешты",
    "cruzești",
    "cruzesti",

    "новые гояны",
    "goianul nou",

    "ревака",
    "revaca",

    "ставчены",
    "stăuceni",
    "stauceni",

    "страшены",
    "strășeni",
    "straseni",

    "сынджера",
    "sîngera",
    "singera",

    "тогатин",
    "tohatin",

    "трушены",
    "trușeni",
    "truseni",

    "фаурешты",
    "făurești",
    "fauresti",

    "фрумушика",
    "frumușica",
    "frumusica",

    "хумулешты",
    "humulești",
    "humulesti",

    "чероборота",
    "cioroborta",

    "чореску",
    "chiorescu",
)


# ============================================================
#                    ЦЕНОВЫЕ ТАБЛИЦЫ
# ============================================================
#
# Структура:
#   категория -> жилой фонд -> район -> комнаты -> (мин, макс)
#
# "Без ремонта, нуждается" использует категорию "Без ремонта".
# ============================================================

PRICE_FILTERS = {

    "Евроремонт": {

        "Новострой": {

            "Центр": {
                1: (70000, 110000),
                2: (100000, 140000),
                3: (130000, 170000),
            },

            "Ботаника": {
                1: (60000, 100000),
                2: (90000, 130000),
                3: (110000, 150000),
            },

            "Рышкановка": {
                1: (60000, 100000),
                2: (90000, 130000),
                3: (110000, 150000),
            },

            "Чеканы": {
                1: (60000, 100000),
                2: (90000, 130000),
                3: (110000, 150000),
            },

            "Буюканы": {
                1: (60000, 100000),
                2: (90000, 130000),
                3: (110000, 150000),
            },

            "Старая Почта": {
                1: (55000, 95000),
                2: (85000, 125000),
                3: (100000, 140000),
            },

            "Скулянка": {
                1: (60000, 100000),
                2: (90000, 130000),
                3: (110000, 150000),
            },

            "Телецентр": {
                1: (60000, 100000),
                2: (90000, 130000),
                3: (110000, 150000),
            },

            "Дурлешты": {
                1: (35000, 75000),
                2: (50000, 90000),
                3: (65000, 105000),
            },
        },

        "Вторичный": {

            "Центр": {
                1: (25000, 65000),
                2: (40000, 80000),
                3: (55000, 95000),
            },

            "Ботаника": {
                1: (25000, 65000),
                2: (40000, 80000),
                3: (55000, 95000),
            },

            "Рышкановка": {
                1: (25000, 65000),
                2: (40000, 80000),
                3: (55000, 95000),
            },

            "Чеканы": {
                1: (25000, 65000),
                2: (40000, 80000),
                3: (55000, 95000),
            },

            "Буюканы": {
                1: (25000, 65000),
                2: (40000, 80000),
                3: (55000, 95000),
            },

            "Старая Почта": {
                1: (20000, 60000),
                2: (35000, 75000),
                3: (50000, 90000),
            },

            "Скулянка": {
                1: (25000, 65000),
                2: (40000, 80000),
                3: (55000, 95000),
            },

            "Телецентр": {
                1: (25000, 65000),
                2: (40000, 80000),
                3: (55000, 95000),
            },
        },
    },

    "Белый вариант": {

        "Новострой": {

            "Центр": {
                1: (60000, 100000),
                2: (80000, 120000),
                3: (110000, 150000),
            },

            "Ботаника": {
                1: (60000, 80000),
                2: (60000, 100000),
                3: (85000, 125000),
            },

            "Рышкановка": {
                1: (60000, 80000),
                2: (60000, 100000),
                3: (85000, 125000),
            },

            "Чеканы": {
                1: (40000, 80000),
                2: (60000, 100000),
                3: (85000, 125000),
            },

            "Буюканы": {
                1: (60000, 80000),
                2: (60000, 100000),
                3: (85000, 125000),
            },

            "Старая Почта": {
                1: (35000, 75000),
                2: (50000, 90000),
                3: (80000, 120000),
            },

            "Скулянка": {
                1: (40000, 80000),
                2: (60000, 100000),
                3: (85000, 125000),
            },

            "Телецентр": {
                1: (40000, 80000),
                2: (60000, 100000),
                3: (85000, 125000),
            },
        },
    },

    "Без ремонта": {

        "Вторичный": {

            "Центр": {
                1: (20000, 60000),
                2: (40000, 80000),
                3: (60000, 100000),
            },

            "Ботаника": {
                1: (15000, 55000),
                2: (25000, 65000),
                3: (35000, 75000),
            },

            "Рышкановка": {
                1: (15000, 55000),
                2: (25000, 65000),
                3: (35000, 75000),
            },

            "Чеканы": {
                1: (15000, 55000),
                2: (25000, 65000),
                3: (35000, 75000),
            },

            "Буюканы": {
                1: (15000, 55000),
                2: (25000, 65000),
                3: (35000, 75000),
            },

            "Старая Почта": {
                1: (10000, 50000),
                2: (20000, 60000),
            },

            "Скулянка": {
                1: (15000, 55000),
                2: (25000, 65000),
                3: (35000, 75000),
            },

            "Телецентр": {
                1: (15000, 55000),
                2: (25000, 65000),
                3: (35000, 75000),
            },
        },
    },

    "Косметический ремонт": {

        "Вторичный": {

            "Центр": {
                1: (35000, 75000),
                2: (50000, 90000),
                3: (70000, 110000),
            },

            "Ботаника": {
                1: (25000, 65000),
                2: (35000, 75000),
                3: (50000, 90000),
            },

            "Рышкановка": {
                1: (35000, 75000),
                2: (35000, 75000),
                3: (50000, 90000),
            },

            "Чеканы": {
                1: (25000, 65000),
                2: (35000, 75000),
                3: (45000, 85000),
            },

            "Буюканы": {
                1: (25000, 65000),
                2: (35000, 75000),
                3: (50000, 90000),
            },

            "Старая Почта": {
                1: (30000, 70000),
                2: (30000, 70000),
                3: (40000, 80000),
            },

            "Скулянка": {
                1: (35000, 75000),
                2: (35000, 75000),
                3: (50000, 90000),
            },

            "Телецентр": {
                1: (35000, 75000),
                2: (35000, 75000),
                3: (50000, 90000),
            },
        },
    },
}


# ============================================================
#                         DATABASE
# ============================================================

def init_database():

    with sqlite3.connect(DB_FILE) as connection:

        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seen_ads (
                ad_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                current_price INTEGER,
                last_seen_price INTEGER,
                last_sent_price INTEGER,
                category TEXT,
                housing_type TEXT,
                district TEXT,
                rooms INTEGER,
                seller_type TEXT,
                city TEXT,
                repair_subtype TEXT,
                last_sent_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("PRAGMA table_info(seen_ads)")

        columns = {
            row[1]
            for row in cursor.fetchall()
        }

        required = {
            "current_price": "INTEGER",
            "last_seen_price": "INTEGER",
            "last_sent_price": "INTEGER",
            "category": "TEXT",
            "housing_type": "TEXT",
            "district": "TEXT",
            "rooms": "INTEGER",
            "seller_type": "TEXT",
            "city": "TEXT",
            "repair_subtype": "TEXT",
            "last_sent_at": "TEXT",
            "updated_at": "TEXT",
        }

        for column, column_type in required.items():

            if column not in columns:

                cursor.execute(
                    f"ALTER TABLE seen_ads "
                    f"ADD COLUMN {column} {column_type}"
                )


def get_seen_ad(ad_id):

    with sqlite3.connect(DB_FILE) as connection:

        connection.row_factory = sqlite3.Row

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM seen_ads
            WHERE ad_id = ?
            """,
            (ad_id,)
        )

        row = cursor.fetchone()

        return dict(row) if row else None


def save_ad_state(ad, sent=False):

    category = ad.get("repair_category")
    housing_type = ad.get("housing_type")
    price = ad.get("price")

    existing = get_seen_ad(ad["id"])

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    with sqlite3.connect(DB_FILE) as connection:

        cursor = connection.cursor()

        if existing is None:

            cursor.execute(
                """
                INSERT INTO seen_ads (
                    ad_id,
                    url,
                    current_price,
                    last_seen_price,
                    last_sent_price,
                    category,
                    housing_type,
                    district,
                    rooms,
                    seller_type,
                    city,
                    repair_subtype,
                    last_sent_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ad["id"],
                    ad["url"],
                    price,
                    price,
                    price if sent else None,
                    category,
                    housing_type,
                    ad.get("district"),
                    ad.get("rooms"),
                    ad.get("seller_type"),
                    ad.get("city"),
                    ad.get("repair_subtype"),
                    now if sent else None,
                    now,
                )
            )

        elif sent:

            cursor.execute(
                """
                UPDATE seen_ads
                SET
                    url = ?,
                    current_price = ?,
                    last_seen_price = ?,
                    last_sent_price = ?,
                    category = ?,
                    housing_type = ?,
                    district = ?,
                    rooms = ?,
                    seller_type = ?,
                    city = ?,
                    repair_subtype = ?,
                    last_sent_at = ?,
                    updated_at = ?
                WHERE ad_id = ?
                """,
                (
                    ad["url"],
                    price,
                    price,
                    price,
                    category,
                    housing_type,
                    ad.get("district"),
                    ad.get("rooms"),
                    ad.get("seller_type"),
                    ad.get("city"),
                    ad.get("repair_subtype"),
                    now,
                    now,
                    ad["id"],
                )
            )

        else:

            cursor.execute(
                """
                UPDATE seen_ads
                SET
                    url = ?,
                    current_price = ?,
                    last_seen_price = ?,
                    category = ?,
                    housing_type = ?,
                    district = ?,
                    rooms = ?,
                    seller_type = ?,
                    city = ?,
                    repair_subtype = ?,
                    updated_at = ?
                WHERE ad_id = ?
                """,
                (
                    ad["url"],
                    price,
                    price,
                    category,
                    housing_type,
                    ad.get("district"),
                    ad.get("rooms"),
                    ad.get("seller_type"),
                    ad.get("city"),
                    ad.get("repair_subtype"),
                    now,
                    ad["id"],
                )
            )


# ============================================================
#                         TEXT HELPERS
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    return " ".join(text.split())


def clean_lines(text):

    return [
        normalize_text(line)
        for line in text.splitlines()
        if normalize_text(line)
    ]


def extract_ad_id(url):

    match = re.search(
        r"/(?:ru/|ro/)?(\d+)(?:\?|/|$)",
        url
    )

    return match.group(1) if match else None


def parse_price(text):

    if not text:
        return None

    matches = re.findall(
        r"(\d[\d\s,.]*)\s*€",
        text
    )

    if not matches:
        return None

    # Берём первое значение с €.
    value = matches[0]

    value = (
        value
        .replace(" ", "")
        .replace(",", "")
        .replace(".", "")
    )

    try:
        return int(value)
    except ValueError:
        return None


def value_after_label(lines, labels):

    normalized_labels = [
        label.lower()
        for label in labels
    ]

    for index, line in enumerate(lines):

        lower = line.lower()

        # Формат:
        # "Жилой фонд Новострой"
        for label in normalized_labels:

            if label in lower:

                after = re.split(
                    re.escape(label),
                    line,
                    maxsplit=1,
                    flags=re.IGNORECASE
                )

                if len(after) == 2:

                    value = normalize_text(
                        after[1].strip(" :-\t")
                    )

                    if value:
                        return value

        # Формат:
        # "Жилой фонд"
        # "Новострой"
        if lower.strip(" :-") in normalized_labels:

            for next_index in range(
                index + 1,
                min(index + 4, len(lines))
            ):

                candidate = lines[next_index].strip()

                if candidate:
                    return candidate

    return None


# ============================================================
#                         РАЙОНЫ
# ============================================================

ALLOWED_DISTRICT_ALIASES = {

    "Старая Почта": (
        "старая почта",
        "poșta veche",
        "posta veche",
    ),

    "Рышкановка": (
        "рышкановка",
        "rîșcani",
        "riscani",
        "ricani",
    ),

    "Ботаника": (
        "ботаника",
        "botanica",
    ),

    "Буюканы": (
        "буюканы",
        "buiucani",
    ),

    "Чеканы": (
        "чеканы",
        "чокана",
        "ciocana",
    ),

    "Скулянка": (
        "скулянка",
        "sculeanca",
    ),

    "Телецентр": (
        "телецентр",
        "telecentru",
    ),

    "Центр": (
        "центр",
        "centru",
    ),

    "Дурлешты": (
        "дурлешты",
        "durlești",
        "durlesti",
    ),
}


def normalize_location_text(text):
    """Нормализация строки местоположения."""
    if not text:
        return ""

    return normalize_text(text).strip(" ,.;")


def find_location_candidates(page_text, heading_texts=None):
    """
    Возвращает кандидаты на строку местоположения.

    Мы не ищем город по всему body:
    описание объявления может содержать "Кишинёв", "Бельцы",
    "Рышкановка" и т.п. как обычный текст.

    В первую очередь используем заголовки страницы (h1-h6),
    потому что на 999.md фактический адрес отображается
    отдельным заголовком рядом с картой/характеристиками.
    """

    candidates = []

    if heading_texts:
        for item in heading_texts:
            value = normalize_location_text(item)
            if value:
                candidates.append(value)

    # Затем строки body.
    for line in clean_lines(page_text):
        value = normalize_location_text(line)
        if value:
            candidates.append(value)

    return candidates


def is_address_like_line(line):
    """
    Определяет, похожа ли строка на реальный адрес.
    Это защищает от случайного совпадения слова "Центр"
    или названия района в описании.
    """

    lower = line.lower()

    address_markers = (
        " str. ",
        " str.",
        " strada ",
        "ул. ",
        "улица ",
        ", mun.",
        " мун.",
        "chișinău",
        "chisinau",
        "кишинёв",
        "кишинев",
        "оргеев",
        "орехей",
        "оргеев",
        "бельцы",
        "balti",
        "bălți",
        "balti",
    )

    if any(marker in lower for marker in address_markers):
        return True

    # Адрес 999.md часто содержит 2-4 частей через запятую.
    if lower.count(",") >= 2:
        return True

    return False


def find_location_line(page_text, heading_texts=None):
    """
    Ищет именно строку фактического местоположения.

    Важно: мы НЕ определяем город/район по произвольному
    упоминанию слов в описании.
    """

    candidates = []

    if heading_texts:
        for item in heading_texts:
            value = normalize_location_text(item)
            if value:
                candidates.append(value)

    candidates.extend(clean_lines(page_text))

    # На 999.md адрес обычно выглядит как строка с несколькими
    # частями через запятую или содержит str./ул./мун.
    for line in candidates:

        lower = line.lower()

        if (
            "кишинёв мун." in lower
            or "кишинев мун." in lower
            or "chișinău mun." in lower
            or "chisinau mun." in lower
            or lower.count(",") >= 2
            or " str." in lower
            or " strada " in lower
            or "ул. " in lower
        ):
            return line

    return None


def is_exact_chisinau_location(location_line):
    """
    True только если конкретная строка адреса относится
    к самому Кишинёву.

    Примеры:
      Кишинёв мун., Ботаника, ... -> True
      Кишинёв мун., Центр, ... -> True
      Кишинёв мун., Дурлешты, ... -> False
      Оргеев, Оргеев, Центр, ... -> False
      8 квартал, Бельцы, Бельцы мун. -> False
    """

    if not location_line:
        return False

    lower = normalize_location_text(
        location_line
    ).lower()

    # ========================================================
    # Сначала обязательно убеждаемся, что это Кишинёв.
    # ========================================================

    has_chisinau = any(
        marker in lower
        for marker in (
            "кишинёв мун.",
            "кишинев мун.",
            "chișinău mun.",
            "chisinau mun.",
            "кишинёв,",
            "кишинев,",
            "chișinău,",
            "chisinau,",
        )
    )

    if not has_chisinau:
        return False

    # ========================================================
    # Любой другой населённый пункт = НЕТ.
    # ========================================================

    for outside in OUTSIDE_CHISINAU:

        if outside in lower:

            logging.info(
                f"LOCATION REJECT: {location_line}"
            )

            return False

    # ========================================================
    # И главное: должен быть именно один из твоих районов.
    # Это не позволяет принять просто "Кишинёв мун."
    # ========================================================

    for district, aliases in ALLOWED_DISTRICT_ALIASES.items():

        if any(
            alias in lower
            for alias in aliases
        ):
            return True

    return False


def find_district_from_location(location_line):

    if not is_exact_chisinau_location(
        location_line
    ):
        return None

    lower = normalize_location_text(
        location_line
    ).lower()

    priority = (
        "Старая Почта",
        "Рышкановка",
        "Ботаника",
        "Буюканы",
        "Чеканы",
        "Скулянка",
        "Телецентр",
        "Центр",
    )

    for district in priority:

        for alias in ALLOWED_DISTRICT_ALIASES[
            district
        ]:

            if alias in lower:
                return district

    return None


def find_city_from_location(location_line):

    if not is_exact_chisinau_location(
        location_line
    ):
        return None

    lower = normalize_location_text(
        location_line
    ).lower()

    if any(
        alias in lower
        for alias in ALLOWED_DISTRICT_ALIASES["Дурлешты"]
    ):
        return "Дурлешты"

    return "Кишинёв"


# ============================================================
#                       HOUSING TYPE
# ============================================================

def find_housing_type(lines, text):

    # Сначала читаем конкретное поле.
    field = value_after_label(
        lines,
        (
            "Жилой фонд",
            "Жилий фонд",
            "Житловий фонд",
            "Fond locativ",
        )
    )

    if field:

        field_lower = field.lower()

        if "новострой" in field_lower:
            return "Новострой"

        if "вторичн" in field_lower:
            return "Вторичный"

        if "secund" in field_lower:
            return "Вторичный"


    # Fallback.
    lower = text.lower()

    if re.search(
        r"жилой\s+фонд.*новострой|"
        r"\bновострой\b|новостройк",
        lower,
        re.IGNORECASE
    ):

        return "Новострой"


    if re.search(
        r"жилой\s+фонд.*вторичн|"
        r"\bвторичный\b|"
        r"fond\s+locativ.*secund",
        lower,
        re.IGNORECASE
    ):

        return "Вторичный"


    return None


# ============================================================
#                       SELLER TYPE
# ============================================================

def find_seller_type(lines, text):

    field = value_after_label(
        lines,
        (
            "Автор объявления",
            "Autorul anunțului",
            "Autorul anuntului",
        )
    )

    if field:

        lower = field.lower()

        if (
            "частное лицо" in lower
            or "persoană fizică" in lower
            or "persoana fizica" in lower
        ):

            return "Частное лицо"


        if (
            "агентство" in lower
            or "agenție" in lower
            or "agentie" in lower
        ):

            return "Агентство"


    lower = text.lower()

    if (
        "частное лицо" in lower
        or "persoană fizică" in lower
        or "persoana fizica" in lower
    ):

        return "Частное лицо"


    if (
        "агентство" in lower
        or "agenție" in lower
        or "agentie" in lower
    ):

        return "Агентство"


    return None


# ============================================================
#                       REPAIR CATEGORY
# ============================================================

def find_repair_category(lines, text):

    field = value_after_label(
        lines,
        (
            "Ремонт",
            "Состояние ремонта",
            "Отделка",
            "Reparație",
            "Reparatie",
        )
    )


    source = (
        field
        if field
        else text
    )


    lower = source.lower()


    # Сначала самая конкретная формулировка.
    need_repair_patterns = (

        "без ремонта, нуждается",
        "без ремонта , нуждается",
        "без ремонта, требует ремонта",
        "без ремонта, требуется ремонт",
        "нуждается в ремонте",
        "требует ремонта",

        "necesită reparație",
        "necesita reparatie",
    )


    for pattern in need_repair_patterns:

        if pattern in lower:

            return "Без ремонта"


    euro_patterns = (

        "евроремонт",
        "евро ремонт",
        "евро-ремонт",
        "euroremont",
        "euro reparatie",
        "euro reparație",
    )


    for pattern in euro_patterns:

        if pattern in lower:

            return "Евроремонт"


    white_patterns = (

        "белый вариант",
        "вариант альба",
        "varianta alba",
        "varianta albă",
    )


    for pattern in white_patterns:

        if pattern in lower:

            return "Белый вариант"


    cosmetic_patterns = (

        "косметический ремонт",
        "косметический",
        "косм ремонт",
        "косм. ремонт",
        "reparatie cosmetica",
        "reparație cosmetică",
    )


    for pattern in cosmetic_patterns:

        if pattern in lower:

            return "Косметический ремонт"


    no_repair_patterns = (

        "без ремонта",
        "без отделки",
        "fara reparatie",
        "fără reparație",
    )


    for pattern in no_repair_patterns:

        if pattern in lower:

            return "Без ремонта"


    return None


def find_repair_subtype(lines, text):

    field = value_after_label(
        lines,
        (
            "Ремонт",
            "Состояние ремонта",
            "Отделка",
            "Reparație",
            "Reparatie",
        )
    )


    source = field if field else text
    lower = source.lower()


    need_patterns = (

        "без ремонта, нуждается",
        "без ремонта , нуждается",
        "без ремонта, требует ремонта",
        "без ремонта, требуется ремонт",
        "нуждается в ремонте",
        "требует ремонта",

        "necesită reparație",
        "necesita reparatie",
    )


    for pattern in need_patterns:

        if pattern in lower:

            return "Без ремонта, нуждается"


    if "без ремонта" in lower:

        return "Без ремонта"


    return None


# ============================================================
#                         ROOMS
# ============================================================

def find_rooms(text):

    lower = text.lower()

    patterns = (

        r"(\d+)[-\s]комнатная",
        r"(\d+)[-\s]комнатной",
        r"(\d+)[-\s]комнатную",
        r"(\d+)[-\s]комнат",
        r"(\d+)\s+camere",
        r"(\d+)\s+camera",
    )


    for pattern in patterns:

        match = re.search(
            pattern,
            lower
        )

        if match:

            try:
                return int(match.group(1))
            except ValueError:
                pass


    return None


# ============================================================
#                         AREA
# ============================================================

def find_area(text):

    patterns = (

        r"(\d+(?:[,.]\d+)?)\s*м²",
        r"(\d+(?:[,.]\d+)?)\s*m²",
        r"(\d+(?:[,.]\d+)?)\s*m2",
    )


    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            return (
                match.group(1)
                .replace(",", ".")
            )


    return None


# ============================================================
#                         FLOOR
# ============================================================

def find_floor(text):

    patterns = (

        r"(\d+)\s*этаж",
        r"этаж\s*(\d+)",
        r"etaj\s*(\d+)",
        r"etajul\s*(\d+)",
    )


    for pattern in patterns:

        match = re.search(
            pattern,
            text.lower()
        )

        if match:

            return match.group(1)


    return None


# ============================================================
#                      PRICE RULE
# ============================================================

def get_price_rule(ad):

    category = ad.get(
        "repair_category"
    )

    housing_type = ad.get(
        "housing_type"
    )

    district = ad.get(
        "district"
    )

    rooms = ad.get(
        "rooms"
    )


    if not all(
        (
            category,
            housing_type,
            district,
        )
    ):

        return None


    if rooms is None:

        return None


    category_rules = PRICE_FILTERS.get(
        category
    )


    if not category_rules:

        return None


    fund_rules = category_rules.get(
        housing_type
    )


    if not fund_rules:

        return None


    district_rules = fund_rules.get(
        district
    )


    if not district_rules:

        return None


    return district_rules.get(
        rooms
    )


# ============================================================
#                       FILTERS
# ============================================================

def matches_filters(ad):

    # --------------------------------------------------------
    # ГОРОД
    # --------------------------------------------------------

    if REQUIRE_CHISINAU:

        if ad.get("city") not in (
            "Кишинёв",
            "Дурлешты",
        ):

            logging.info(
                f"{ad['id']} | Отклонено: "
                f"точное местоположение = "
                f"{ad.get('location_line')}"
            )

            return False


    # --------------------------------------------------------
    # РАЙОН
    # --------------------------------------------------------

    if ad.get("district") not in ALLOWED_DISTRICTS:

        return False


    # --------------------------------------------------------
    # ЧАСТНОЕ ЛИЦО
    # --------------------------------------------------------

    if REQUIRE_PRIVATE_PERSON:

        if ad.get("seller_type") != "Частное лицо":

            return False


    # --------------------------------------------------------
    # ЖИЛОЙ ФОНД
    # --------------------------------------------------------

    if REQUIRE_HOUSING_TYPE:

        if ad.get("housing_type") not in (
            "Новострой",
            "Вторичный",
        ):

            return False


    # --------------------------------------------------------
    # ЦЕНА
    # --------------------------------------------------------

    if ad.get("price") is None:

        return False


    # --------------------------------------------------------
    # КОМНАТЫ
    # --------------------------------------------------------

    if ad.get("rooms") is None:

        return False


    if ROOMS and ad["rooms"] not in ROOMS:

        return False


    # --------------------------------------------------------
    # РЕМОНТ
    # --------------------------------------------------------

    if ad.get("repair_category") is None:

        return False


    # --------------------------------------------------------
    # ЦЕНОВОЕ ПРАВИЛО
    # --------------------------------------------------------

    price_rule = get_price_rule(
        ad
    )


    if price_rule is None:

        return False


    min_price, max_price = price_rule


    if not (
        min_price
        <= ad["price"]
        <= max_price
    ):

        return False


    return True


# ============================================================
#                  PRICE CHANGE CHECK
# ============================================================

def has_price_decreased(
    ad,
    old_state
):

    if old_state is None:

        return False


    old_price = old_state.get(
        "last_seen_price"
    )

    new_price = ad.get(
        "price"
    )


    if old_price is None:

        return False


    if new_price is None:

        return False


    return new_price < old_price


# ============================================================
#                    TELEGRAM MESSAGE
# ============================================================

def format_price(price):

    if price is None:

        return "Не указана"

    return (
        f"{price:,}"
        .replace(",", " ")
        + " €"
    )


def build_message(
    ad,
    price_drop=False,
    old_price=None,
    test=False
):

    if test:

        header = (
            "🧪 <b>ТЕСТОВОЕ ОБЪЯВЛЕНИЕ</b>\n\n"
        )

    elif price_drop:

        header = (
            "🔥 <b>ЦЕНА СНИЖЕНА</b>\n\n"
        )

    else:

        header = (
            "🏠 <b>НОВОЕ ОБЪЯВЛЕНИЕ</b>\n\n"
        )


    message = header


    if (
        price_drop
        and old_price is not None
    ):

        message += (
            f"💸 <b>Было:</b> "
            f"<s>{format_price(old_price)}</s>\n"
            f"🔥 <b>Стало:</b> "
            f"<b>{format_price(ad['price'])}</b>\n\n"
        )

    else:

        message += (
            f"💰 <b>Цена:</b> "
            f"{format_price(ad['price'])}\n\n"
        )


    message += (

        f"📌 <b>{ad['title']}</b>\n\n"

        f"👤 <b>Автор:</b> "
        f"{ad.get('seller_type') or 'Не определён'}\n"

        f"🏙 <b>Город:</b> "
        f"{ad.get('city') or 'Не определён'}\n"

        f"📍 <b>Район:</b> "
        f"{ad.get('district') or 'Не определён'}\n"

        f"🛏 <b>Комнат:</b> "
        f"{ad.get('rooms') or 'Не указано'}\n"

        f"📐 <b>Площадь:</b> "
        f"{ad.get('area') or 'Не указана'} м²\n"

        f"🏢 <b>Этаж:</b> "
        f"{ad.get('floor') or 'Не указан'}\n"

        f"🏗 <b>Жилой фонд:</b> "
        f"{ad.get('housing_type') or 'Не определён'}\n"

        f"🛠 <b>Ремонт:</b> "
        f"{ad.get('repair_subtype') or ad.get('repair_category') or 'Не определён'}\n\n"

        f"🔗 <a href=\"{ad['url']}\">"
        f"Открыть объявление"
        f"</a>"
    )


    return message


async def send_ad(
    bot,
    ad,
    price_drop=False,
    old_price=None,
    test=False
):

    message = build_message(
        ad,
        price_drop=price_drop,
        old_price=old_price,
        test=test
    )


    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Открыть объявление",
                    url=ad["url"]
                )
            ]
        ]
    )


    try:

        if ad.get("image"):

            try:

                await bot.send_photo(
                    chat_id=CHAT_ID,
                    photo=ad["image"],
                    caption=message,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

                return True

            except Exception as error:

                logging.warning(
                    f"{ad['id']} | "
                    f"Фото не отправилось: {error}"
                )


        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="HTML",
            reply_markup=keyboard
        )

        return True


    except Exception as error:

        logging.exception(
            f"{ad['id']} | "
            f"Ошибка Telegram: {error}"
        )

        return False


# ============================================================
#                 TELEGRAM CONNECTION TEST
# ============================================================

async def telegram_test(bot):

    try:

        await bot.send_message(
            chat_id=CHAT_ID,
            text=(
                "✅ <b>999.md БОТ ЗАПУЩЕН</b>\n\n"
                "Telegram работает.\n"
                "Начинаю поиск объявлений..."
            ),
            parse_mode="HTML"
        )

        logging.info(
            "Telegram подключён."
        )

        return True


    except Exception as error:

        logging.error(
            f"Telegram error: {error}"
        )

        return False


# ============================================================
#              GET LISTING LINKS
# ============================================================

async def get_listing_links(page):

    logging.info(
        "Открываем список 999.md и собираем все доступные страницы..."
    )

    result = {}

    # Сначала открываем первую страницу.
    try:
        await page.goto(
            LISTING_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )
    except PlaywrightTimeoutError:
        logging.warning(
            "Таймаут открытия первой страницы 999.md. "
            "Продолжаем чтение уже загруженного DOM."
        )

    await page.wait_for_timeout(3000)

    # Собираем страницы пагинации из самой выдачи.
    pagination_urls = []

    try:
        page_links = await page.locator(
            "a[href]"
        ).evaluate_all(
            """
            elements => elements.map(a => ({
                href: a.href,
                text: (a.innerText || "").trim()
            }))
            """
        )

        for item in page_links:
            href = item.get("href", "")
            if not href:
                continue

            href = urljoin(BASE_URL, href)

            # Берём только ссылки пагинации 999.md.
            if "999.md" not in href:
                continue

            if re.search(r"(?:[?&])page=\d+", href):
                pagination_urls.append(href)

    except Exception as error:
        logging.warning(
            f"Не удалось определить пагинацию: {error}"
        )

    # Если пагинация не обнаружена, всё равно обрабатываем первую страницу.
    pages = [LISTING_URL]

    # Сортируем по номеру page= и ограничиваем MAX_LISTING_PAGES.
    unique_pages = []
    seen_pages = set()

    for url in pagination_urls:
        if url not in seen_pages:
            seen_pages.add(url)
            unique_pages.append(url)

    def page_number(url):
        match = re.search(r"(?:[?&])page=(\d+)", url)
        return int(match.group(1)) if match else 1

    unique_pages.sort(key=page_number)

    for url in unique_pages:
        if url != LISTING_URL:
            pages.append(url)

    pages = pages[:MAX_LISTING_PAGES]

    logging.info(
        f"Страниц выдачи для проверки: {len(pages)}"
    )

    # Обрабатываем каждую страницу.
    for page_index, listing_url in enumerate(pages, start=1):

        if page_index > 1:
            try:
                await page.goto(
                    listing_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )
            except PlaywrightTimeoutError:
                logging.warning(
                    f"Таймаут страницы выдачи #{page_index}: "
                    f"{listing_url}"
                )

            await page.wait_for_timeout(2000)

        try:
            links = await page.locator(
                "a[href]"
            ).evaluate_all(
                """
                elements => elements.map(a => ({
                    href: a.href,
                    text: a.innerText || ""
                }))
                """
            )
        except Exception as error:
            logging.warning(
                f"Не удалось получить ссылки со страницы "
                f"#{page_index}: {error}"
            )
            continue

        before = len(result)

        for item in links:

            href = item.get(
                "href",
                ""
            )

            if not href:
                continue

            href = urljoin(
                BASE_URL,
                href
            )

            ad_id = extract_ad_id(
                href
            )

            if not ad_id:
                continue

            if "999.md" not in href:
                continue

            # Не считаем пагинацию объявлением.
            if re.search(
                r"(?:[?&])page=\d+",
                href
            ) and not re.search(
                r"/\d+(?:\?|/|$)",
                href
            ):
                continue

            result[ad_id] = {
                "id": ad_id,
                "url": href
            }

        added = len(result) - before

        logging.info(
            f"Страница выдачи #{page_index}: "
            f"+{added} объявлений, всего {len(result)}"
        )

    logging.info(
        f"Ссылок на объявления найдено всего: {len(result)}"
    )

    if not result:

        try:

            await page.screenshot(
                path="999_debug.png",
                full_page=True
            )

            with open(
                "999_debug.html",
                "w",
                encoding="utf-8"
            ) as file:

                file.write(
                    await page.content()
                )

            logging.warning(
                "Созданы 999_debug.png и 999_debug.html."
            )

        except Exception as error:

            logging.error(
                f"DEBUG error: {error}"
            )

    return list(
        result.values()
    )


# ============================================================
#                    PARSE AD
# ============================================================

async def parse_ad(
    page,
    ad
):

    try:

        logging.info(
            f"Открываем объявление {ad['id']}..."
        )


        try:

            await page.goto(
                ad["url"],
                wait_until="domcontentloaded",
                timeout=60000
            )

        except PlaywrightTimeoutError:

            logging.warning(
                f"{ad['id']} | "
                "Таймаут страницы, продолжаем чтение."
            )


        await page.wait_for_timeout(
            1200
        )


        body_text = await page.locator(
            "body"
        ).inner_text()


        lines = clean_lines(
            body_text
        )


        text = normalize_text(
            body_text
        )


        title = normalize_text(
            await page.title()
        )


        # ----------------------------------------------------
        # МЕСТОПОЛОЖЕНИЕ
        # ----------------------------------------------------
        #
        # Получаем заголовки h1-h6. На 999.md фактический
        # адрес находится в отдельном блоке страницы.
        # ----------------------------------------------------

        heading_texts = await page.locator(
            "h1, h2, h3, h4, h5, h6"
        ).all_inner_texts()


        location_line = find_location_line(
            body_text,
            heading_texts
        )


        city = find_city_from_location(
            location_line
        )


        district = find_district_from_location(
            location_line
        )


        seller_type = find_seller_type(
            lines,
            text
        )


        housing_type = find_housing_type(
            lines,
            text
        )


        rooms = find_rooms(
            text
        )


        price = parse_price(
            text
        )


        area = find_area(
            text
        )


        floor = find_floor(
            text
        )


        repair_category = find_repair_category(
            lines,
            text
        )


        repair_subtype = find_repair_subtype(
            lines,
            text
        )


        # ----------------------------------------------------
        # Фото
        # ----------------------------------------------------

        image = None


        images = await page.locator(
            "img"
        ).evaluate_all(
            """
            elements => elements
                .map(img => img.src)
                .filter(Boolean)
            """
        )


        for image_url in images:

            if (
                isinstance(image_url, str)
                and image_url.startswith("http")
                and "999.md" in image_url
            ):

                image = image_url
                break


        ad_data = {

            "id": ad["id"],

            "url": ad["url"],

            "title": title or "Квартира",

            "city": city,

            "district": district,

            "location_line": location_line,

            "seller_type": seller_type,

            "housing_type": housing_type,

            "rooms": rooms,

            "price": price,

            "area": area,

            "floor": floor,

            "repair_category": repair_category,

            "repair_subtype": repair_subtype,

            "image": image,

        }


        logging.info(
            f"{ad['id']} | "
            f"location={location_line} | "
            f"точный_Кишинёв={'ДА' if city == 'Кишинёв' else 'НЕТ'} | "
            f"город={city} | "
            f"район={district} | "
            f"автор={seller_type} | "
            f"фонд={housing_type} | "
            f"ремонт={repair_subtype or repair_category} | "
            f"комнат={rooms} | "
            f"цена={price}"
        )


        return ad_data


    except Exception as error:

        logging.exception(
            f"{ad['id']} | "
            f"Ошибка парсинга: {error}"
        )

        return None


# ============================================================
#                    MAIN CHECK
# ============================================================

async def check_999(
    page,
    bot,
    first_run=False
):

    ads = await get_listing_links(
        page
    )


    if not ads:

        return


    # --------------------------------------------------------
    # Тестовая отправка
    # --------------------------------------------------------

    if (
        TEST_SEND_FIRST_AD
        and first_run
    ):

        for ad in ads:

            parsed = await parse_ad(
                page,
                ad
            )


            if not parsed:
                continue


            if await send_ad(
                bot,
                parsed,
                test=True
            ):

                save_ad_state(
                    parsed,
                    sent=True
                )


            break


    # --------------------------------------------------------
    # Основная обработка
    # --------------------------------------------------------

    for ad in ads:

        parsed = await parse_ad(
            page,
            ad
        )


        if not parsed:

            continue


        old_state = get_seen_ad(
            parsed["id"]
        )


        # ----------------------------------------------------
        # Проверка соответствия текущим фильтрам
        # ----------------------------------------------------

        if not matches_filters(
            parsed
        ):

            # Обязательно сохраняем цену.
            # Если завтра цена станет ниже и квартира
            # начнёт подходить — бот сможет её отправить.
            save_ad_state(
                parsed,
                sent=False
            )

            continue


        # ----------------------------------------------------
        # НОВОЕ ОБЪЯВЛЕНИЕ
        # ----------------------------------------------------

        if old_state is None:

            logging.info(
                f"{parsed['id']} | "
                "НОВОЕ подходящее объявление."
            )


            if await send_ad(
                bot,
                parsed
            ):

                save_ad_state(
                    parsed,
                    sent=True
                )


            await asyncio.sleep(
                1
            )

            continue


        # ----------------------------------------------------
        # РАНЕЕ ИЗВЕСТНОЕ, НО ЕЩЁ НЕ ОТПРАВЛЯЛОСЬ
        # ----------------------------------------------------

        if old_state.get(
            "last_sent_price"
        ) is None:

            logging.info(
                f"{parsed['id']} | "
                "Теперь подходит — отправляем."
            )


            if await send_ad(
                bot,
                parsed
            ):

                save_ad_state(
                    parsed,
                    sent=True
                )


            await asyncio.sleep(
                1
            )

            continue


        # ----------------------------------------------------
        # ЦЕНА СНИЗИЛАСЬ
        # ----------------------------------------------------

        if has_price_decreased(
            parsed,
            old_state
        ):

            old_price = old_state.get(
                "last_seen_price"
            )


            logging.info(
                f"{parsed['id']} | "
                f"ЦЕНА СНИЗИЛАСЬ: "
                f"{old_price} -> "
                f"{parsed['price']}"
            )


            if await send_ad(
                bot,
                parsed,
                price_drop=True,
                old_price=old_price
            ):

                save_ad_state(
                    parsed,
                    sent=True
                )


        else:

            # Только обновляем текущую цену.
            save_ad_state(
                parsed,
                sent=False
            )


        await asyncio.sleep(
            1
        )


# ============================================================
#                         MAIN
# ============================================================

async def main():

    # --------------------------------------------------------
    # Проверка конфигурации
    # --------------------------------------------------------

    if (
        not BOT_TOKEN
        or BOT_TOKEN.startswith("ВСТАВЬ_")
    ):

        raise RuntimeError(
            "Не указан BOT_TOKEN. "
            "Вставь новый токен от @BotFather."
        )


    if not CHAT_ID:

        raise RuntimeError(
            "Не указан CHAT_ID."
        )


    init_database()


    bot = Bot(
        token=BOT_TOKEN
    )


    try:

        # ----------------------------------------------------
        # Telegram
        # ----------------------------------------------------

        if TEST_TELEGRAM:

            telegram_ok = await telegram_test(
                bot
            )


            if not telegram_ok:

                return


        # ----------------------------------------------------
        # Playwright
        # ----------------------------------------------------

        async with async_playwright() as playwright:

            print("1/4 Playwright запускается...", flush=True)
            logging.info("1/4 Playwright запускается.")


            try:

                browser = await asyncio.wait_for(

                    playwright.chromium.launch(
                        headless=True
                    ),

                    timeout=30
                )

            except asyncio.TimeoutError as error:

                raise RuntimeError(
                    "Chromium не запустился за 30 секунд. "
                    "Проверь установку браузеров Playwright."
                ) from error


            print("2/4 Chromium запущен.", flush=True)
            logging.info("2/4 Chromium запущен.")


            context = await browser.new_context(

                locale="ru-RU",

                viewport={
                    "width": 1440,
                    "height": 900
                },

                user_agent=(
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/153.0.0.0 "
                    "Safari/537.36"
                )
            )


            page = await context.new_page()


            print("3/4 Страница браузера создана.", flush=True)
            logging.info("3/4 Страница браузера создана.")


            print("4/4 Начинаю поиск 999.md...", flush=True)
            logging.info("4/4 Начинаю поиск 999.md.")


            logging.info(
                "Разрешённые районы: "
                + ", ".join(
                    ALLOWED_DISTRICTS
                )
            )

            logging.info(
                "Локации: Кишинёв + Дурлешты. "
                "Остальные населённые пункты исключены."
            )


            logging.info(
                "Фильтр: Частное лицо -> Кишинёв"
            )


            first_run = True


            while True:

                try:

                    await check_999(

                        page,

                        bot,

                        first_run=first_run
                    )


                    first_run = False


                except Exception as error:

                    logging.exception(
                        f"Ошибка цикла проверки: {error}"
                    )


                logging.info(
                    f"Следующая проверка через "
                    f"{CHECK_INTERVAL} сек."
                )


                await asyncio.sleep(
                    CHECK_INTERVAL
                )


    finally:

        logging.info(
            "Закрываем Telegram-сессию..."
        )


        await bot.session.close()


        logging.info(
            "Telegram-сессия закрыта."
        )


# ============================================================
#                         START
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "\nБот остановлен пользователем."
        )

    except Exception as error:

        logging.exception(
            f"Критическая ошибка: {error}"
        )
