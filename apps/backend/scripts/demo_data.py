"""Replace the tenant's master and business data with a realistic demo dataset. Development and demo databases only.

What it does:
  1. Deletes every item, location, business partner, document, stock row, audit entry and integration event of the
     tenant. Kept: the tenant, users, roles, permissions, feature flags, units, reason codes, numbering rules (reset).
  2. Builds master data for a food & beverage distributor in the Klang Valley: one distribution centre with ambient,
     chiller and freezer zones, ~55 SKUs with packing units and barcodes, suppliers, customers and warehouse staff.
  3. Simulates --days days of operations through the real API with a shifted clock, so every document, ledger row,
     balance, doc number and audit entry is what the application itself would have written on that day:
     purchase orders -> goods receipts -> putaway sheets, sales orders -> allocation -> picks -> delivery orders,
     supplier payments, damage and expiry write-offs. Nothing is dated after the real current time, so today's work
     is left half done (orders not yet picked, goods staged for tomorrow's trucks, receipts on the dock).

Usage (in apps/backend):
    python -m scripts.demo_data --confirm [--days 60] [--seed 2026]

Demo staff accounts are created with the password Demo@2026 (or $DEMO_PASSWORD).
"""

import argparse
import datetime as _dt
import math
import os
import random
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import text

# ---------------------------------------------------------------- simulated clock
# The app reads the time through datetime.now()/date.today() in its own modules. Those module globals are swapped for
# subclasses whose now() is shifted by _offset, so the API writes the simulated time everywhere (documents, ledger,
# doc numbers, audit). app.core.security keeps the real clock, so login tokens stay valid.

REAL_DATETIME, REAL_DATE = _dt.datetime, _dt.date
_offset = _dt.timedelta(0)


class _DatetimeMeta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, REAL_DATETIME)


class _DateMeta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, REAL_DATE)


class FakeDatetime(REAL_DATETIME, metaclass=_DatetimeMeta):
    @classmethod
    def now(cls, tz=None):
        return REAL_DATETIME.now(tz) + _offset

    @classmethod
    def utcnow(cls):
        return REAL_DATETIME.now(_dt.UTC).replace(tzinfo=None) + _offset

    @classmethod
    def today(cls):
        return cls.now()


class FakeDate(REAL_DATE, metaclass=_DateMeta):
    @classmethod
    def today(cls):
        return (REAL_DATETIME.now() + _offset).date()


def install_clock() -> None:
    from sqlalchemy.orm import configure_mappers

    import app.main  # noqa: F401  load every module the API uses

    configure_mappers()  # resolve model annotations before the names they use are swapped
    for name, module in list(sys.modules.items()):
        if not name.startswith("app.") or name.startswith(("app.schemas", "app.core.security")):
            continue
        if getattr(module, "datetime", None) is REAL_DATETIME:
            module.datetime = FakeDatetime
        if getattr(module, "date", None) is REAL_DATE:
            module.date = FakeDate


class Clock:
    """Sets the simulated local time. Refuses times after the real current time, so the data never lies in the future."""

    def __init__(self, tz: ZoneInfo):
        self.tz = tz

    def real_now(self) -> REAL_DATETIME:
        return REAL_DATETIME.now(self.tz).replace(tzinfo=None)

    def at(self, day: REAL_DATE, hour: float) -> bool:
        global _offset
        local = REAL_DATETIME.combine(day, _dt.time()) + _dt.timedelta(hours=hour)
        if local > self.real_now() - _dt.timedelta(minutes=2):
            return False
        _offset = local.replace(tzinfo=self.tz) - REAL_DATETIME.now(_dt.UTC)
        return True

    def reset(self) -> None:
        global _offset
        _offset = _dt.timedelta(0)


# ---------------------------------------------------------------- master data definitions

UOMS = [
    ("EA", "Each"), ("CTN", "Carton"), ("PLT", "Pallet"), ("BTL", "Bottle"), ("PKT", "Packet"),
    ("TIN", "Tin"), ("CAN", "Can"), ("BAG", "Bag"), ("TUB", "Tub"), ("BOX", "Box"),
]

# key, code, name, contact, phone, address, credit terms, lead days, order weekdays (0 = Monday), barcode prefix
SUPPLIERS = [
    ("BEV", "S10001", "Tirta Alam Beverages Sdn Bhd", "Kelvin Ong", "+60 3-5191 2277",
     "Lot 8, Jalan Utas 15/7, Seksyen 15, 40200 Shah Alam, Selangor", 30, 2, (0, 3), "9556101"),
    ("DRY", "S10002", "Sinar Dairy Industries Sdn Bhd", "Nor Azlina binti Hassan", "+60 6-677 4810",
     "PT 4521, Kawasan Perindustrian Senawang, 70450 Seremban, Negeri Sembilan", 30, 1, (0, 2, 4), "9556102"),
    ("FRZ", "S10003", "Kembara Frozen Foods Sdn Bhd", "Jason Lee Chee Keong", "+60 3-3343 6091",
     "No. 22, Jalan Kebun Nenas 4, Kawasan Perindustrian Pandamaran, 42000 Port Klang, Selangor", 45, 3, (1, 4), "9556103"),
    ("RIC", "S10004", "Padi Emas Trading Sdn Bhd", "Haji Kamarul Ariffin", "+60 4-733 9152",
     "Lot 1203, Jalan Kuala Kedah, 05400 Alor Setar, Kedah", 60, 4, (0,), "9556104"),
    ("OIL", "S10005", "Seri Murni Food Industries Sdn Bhd", "Priya Devi a/p Nadarajan", "+60 7-251 8836",
     "PLO 145, Jalan Tembaga 2, Kawasan Perindustrian Pasir Gudang, 81700 Pasir Gudang, Johor", 30, 3, (2,), "9556105"),
    ("SNK", "S10006", "Crispy Valley Snacks Sdn Bhd", "Tan Mei Fong", "+60 4-644 2019",
     "Plot 88, Lintang Bayan Lepas 6, Bayan Lepas Industrial Park, 11900 Bayan Lepas, Pulau Pinang", 45, 4, (1,), "9556106"),
    ("CAN", "S10007", "Lautan Biru Canning Sdn Bhd", "Wong Siew Lan", "+60 5-683 4470",
     "Lot 3, Kawasan Perindustrian Kampung Acheh, 32000 Sitiawan, Perak", 60, 5, (3,), "9556107"),
    ("HHC", "S10008", "Bersih Home Care Sdn Bhd", "Mohd Faizal bin Othman", "+60 6-799 3125",
     "No. 15, Jalan BBN 1/3, Bandar Baru Nilai, 71800 Nilai, Negeri Sembilan", 30, 3, (4,), "9556108"),
]

# sku, name, category, demand key, base unit, per carton (None = sold in the base unit), base units per pallet,
# zone, shelf life days (None = not dated), cost per base unit (RM), demand (sale units per day), supplier
ITEMS = [
    ("BEV-1001", "Tirta Mineral Water 500ml", "Beverages", "bev", "BTL", 24, 1920, "AMB", 540, "0.42", 30, "BEV"),
    ("BEV-1002", "Tirta Mineral Water 1.5L", "Beverages", "bev", "BTL", 12, 840, "AMB", 540, "1.05", 18, "BEV"),
    ("BEV-1003", "Segar Isotonic Drink 500ml", "Beverages", "bev", "BTL", 24, 1440, "AMB", 365, "1.60", 8, "BEV"),
    ("BEV-1004", "Segar Chrysanthemum Tea 300ml", "Beverages", "bev", "CAN", 24, 2160, "AMB", 365, "1.10", 6, "BEV"),
    ("BEV-1005", "Segar Soya Bean Drink 1L", "Beverages", "bev", "PKT", 12, 720, "AMB", 270, "2.60", 5, "BEV"),
    ("BEV-1006", "Kopi Pagi 3-in-1 White Coffee 20 x 38g", "Beverages", "bev", "PKT", 24, 1200, "AMB", 540, "9.80", 7, "BEV"),
    ("BEV-1007", "Teh Bukit Tea Dust 1kg", "Beverages", "bev", "PKT", 12, 720, "AMB", 720, "14.50", 3, "BEV"),
    ("DRY-2001", "Sinar Fresh Milk 1L", "Dairy & Chilled", "dairy", "BTL", 12, 600, "CHL", 12, "5.90", 10, "DRY"),
    ("DRY-2002", "Sinar Low Fat Milk 1L", "Dairy & Chilled", "dairy", "BTL", 12, 600, "CHL", 12, "6.20", 4, "DRY"),
    ("DRY-2003", "Sinar Natural Yoghurt 500g", "Dairy & Chilled", "dairy", "TUB", 12, 720, "CHL", 21, "6.40", 3, "DRY"),
    ("DRY-2004", "Sinar Salted Butter 250g", "Dairy & Chilled", "dairy", "PKT", 40, 2400, "CHL", 120, "8.10", 2, "DRY"),
    ("DRY-2005", "Sinar Cheddar Cheese Slices 12s 250g", "Dairy & Chilled", "dairy", "PKT", 24, 1440, "CHL", 150, "9.30", 3, "DRY"),
    ("DRY-2006", "Sinar Whipping Cream 1L", "Dairy & Chilled", "dairy", "PKT", 12, 720, "CHL", 90, "18.50", 2, "DRY"),
    ("DRY-2007", "Sinar Sweetened Creamer 500g", "Dairy (ambient)", "dairy", "TIN", 48, 2400, "AMB", 365, "3.10", 9, "DRY"),
    ("DRY-2008", "Sinar Evaporated Creamer 390g", "Dairy (ambient)", "dairy", "TIN", 48, 2400, "AMB", 365, "2.70", 7, "DRY"),
    ("FRZ-3001", "Kembara Chicken Nuggets 1kg", "Frozen", "frozen", "PKT", 10, 480, "FRZ", 270, "14.20", 4, "FRZ"),
    ("FRZ-3002", "Kembara Chicken Frankfurters 1kg", "Frozen", "frozen", "PKT", 10, 480, "FRZ", 270, "11.80", 4, "FRZ"),
    ("FRZ-3003", "Kembara Beef Burger Patties 20s 1.2kg", "Frozen", "frozen", "BOX", 10, 480, "FRZ", 365, "21.00", 2, "FRZ"),
    ("FRZ-3004", "Kembara Shoestring Fries 2kg", "Frozen", "frozen", "BAG", 6, 300, "FRZ", 540, "13.50", 5, "FRZ"),
    ("FRZ-3005", "Kembara Mixed Vegetables 1kg", "Frozen", "frozen", "BAG", 12, 600, "FRZ", 365, "6.80", 2, "FRZ"),
    ("FRZ-3006", "Kembara Roti Canai Plain 20s", "Frozen", "frozen", "PKT", 6, 360, "FRZ", 270, "12.40", 3, "FRZ"),
    ("RIC-4001", "Padi Emas Local White Rice 10kg", "Rice & Grains", "rice", "BAG", None, 100, "AMB", 365, "26.00", 25, "RIC"),
    ("RIC-4002", "Padi Emas Fragrant Jasmine Rice 5kg", "Rice & Grains", "rice", "BAG", None, 160, "AMB", 365, "21.50", 15, "RIC"),
    ("RIC-4003", "Padi Emas Basmathi Rice 5kg", "Rice & Grains", "rice", "BAG", None, 160, "AMB", 540, "34.00", 4, "RIC"),
    ("RIC-4004", "Padi Emas Glutinous Rice 1kg", "Rice & Grains", "rice", "PKT", 10, 800, "AMB", 365, "4.60", 3, "RIC"),
    ("RIC-4005", "Manis Fine Granulated Sugar 1kg", "Sugar & Flour", "dry", "PKT", 20, 1200, "AMB", 720, "2.85", 14, "RIC"),
    ("RIC-4006", "Seri Mekar All-Purpose Wheat Flour 1kg", "Sugar & Flour", "dry", "PKT", 20, 1200, "AMB", 270, "2.30", 8, "RIC"),
    ("OIL-5001", "Seri Murni Palm Cooking Oil 5kg", "Cooking Oil", "oil", "BTL", 4, 192, "AMB", 540, "27.50", 10, "OIL"),
    ("OIL-5002", "Seri Murni Palm Cooking Oil 2kg", "Cooking Oil", "oil", "BTL", 6, 360, "AMB", 540, "11.90", 6, "OIL"),
    ("OIL-5003", "Seri Murni Pure Sunflower Oil 2L", "Cooking Oil", "oil", "BTL", 6, 360, "AMB", 540, "19.80", 2, "OIL"),
    ("OIL-5004", "Dapur Ibu Chilli Sauce 340g", "Sauces & Condiments", "sauce", "BTL", 24, 1440, "AMB", 540, "3.20", 6, "OIL"),
    ("OIL-5005", "Dapur Ibu Tomato Ketchup 325g", "Sauces & Condiments", "sauce", "BTL", 24, 1440, "AMB", 540, "2.90", 4, "OIL"),
    ("OIL-5006", "Dapur Ibu Thick Soy Sauce 640ml", "Sauces & Condiments", "sauce", "BTL", 12, 720, "AMB", 720, "4.50", 5, "OIL"),
    ("OIL-5007", "Dapur Ibu Oyster Sauce 510g", "Sauces & Condiments", "sauce", "BTL", 12, 720, "AMB", 540, "6.30", 3, "OIL"),
    ("SNK-6001", "Rangup Cream Crackers 428g", "Snacks & Biscuits", "snack", "PKT", 12, 720, "AMB", 270, "5.40", 6, "SNK"),
    ("SNK-6002", "Rangup Marie Biscuits 300g", "Snacks & Biscuits", "snack", "PKT", 24, 1440, "AMB", 270, "3.10", 4, "SNK"),
    ("SNK-6003", "Crispy Valley Potato Chips Original 60g", "Snacks & Biscuits", "snack", "PKT", 48, 1920, "AMB", 180, "2.20", 5, "SNK"),
    ("SNK-6004", "Crispy Valley Prawn Crackers 70g", "Snacks & Biscuits", "snack", "PKT", 48, 1920, "AMB", 180, "1.90", 4, "SNK"),
    ("SNK-6005", "Crispy Valley Instant Noodles Curry 5 x 80g", "Snacks & Biscuits", "snack", "PKT", 8, 640, "AMB", 240, "4.20", 12, "SNK"),
    ("SNK-6006", "Crispy Valley Instant Noodles Chicken 5 x 80g", "Snacks & Biscuits", "snack", "PKT", 8, 640, "AMB", 240, "4.20", 9, "SNK"),
    ("SNK-6007", "Rangup Chocolate Wafer 12 x 20g", "Snacks & Biscuits", "snack", "BOX", 24, 1440, "AMB", 270, "4.80", 3, "SNK"),
    ("CAN-7001", "Lautan Biru Sardines in Tomato Sauce 425g", "Canned Food", "canned", "TIN", 24, 2016, "AMB", 1095, "5.30", 8, "CAN"),
    ("CAN-7002", "Lautan Biru Tuna Chunks in Brine 185g", "Canned Food", "canned", "TIN", 48, 4032, "AMB", 1095, "4.70", 4, "CAN"),
    ("CAN-7003", "Lautan Biru Mackerel in Tomato Sauce 155g", "Canned Food", "canned", "TIN", 48, 4032, "AMB", 1095, "2.60", 4, "CAN"),
    ("CAN-7004", "Ladang Hijau Baked Beans 425g", "Canned Food", "canned", "TIN", 24, 2016, "AMB", 730, "3.20", 3, "CAN"),
    ("CAN-7005", "Ladang Hijau Button Mushrooms 425g", "Canned Food", "canned", "TIN", 24, 2016, "AMB", 1095, "3.90", 2, "CAN"),
    ("CAN-7006", "Ladang Hijau Sweet Corn Kernels 400g", "Canned Food", "canned", "TIN", 24, 2016, "AMB", 730, "3.40", 2, "CAN"),
    ("HHC-8001", "Bersih Dishwashing Liquid Lime 900ml", "Household", "household", "BTL", 12, 720, "AMB", None, "4.10", 6, "HHC"),
    ("HHC-8002", "Bersih Laundry Detergent Powder 2.3kg", "Household", "household", "PKT", 6, 360, "AMB", None, "14.90", 4, "HHC"),
    ("HHC-8003", "Bersih Floor Cleaner Lavender 2L", "Household", "household", "BTL", 6, 360, "AMB", None, "7.90", 3, "HHC"),
    ("HHC-8004", "Wangi Toilet Roll 3-ply 10 Rolls", "Household", "household", "PKT", 6, 180, "AMB", None, "9.80", 5, "HHC"),
    ("HHC-8005", "Wangi Kitchen Towel 2 Rolls", "Household", "household", "PKT", 24, 720, "AMB", None, "4.60", 2, "HHC"),
    ("HHC-8006", "Bersih Hand Soap Refill 450ml", "Household", "household", "PKT", 24, 1440, "AMB", None, "3.60", 2, "HHC"),
    ("HHC-8007", "Bersih Garbage Bags Large 20s", "Household", "household", "PKT", 48, 1920, "AMB", None, "3.20", 3, "HHC"),
]
# Listed but no longer sold: shows up as inactive in master data
DISCONTINUED = ("SNK-6008", "Crispy Valley Seaweed Chips 50g (discontinued)", "Snacks & Biscuits", "PKT", 48, "SNK")

# code, name, kind, size (L/M/S), route, contact, phone, address, order weekdays
CUSTOMERS = [
    ("C20001", "Pasar Mini Mutiara", "MINI", "L", "SA", "Lim Chee Hong", "+60 3-5510 3382",
     "No. 18, Jalan Plumbum 7/102, Seksyen 7, 40000 Shah Alam, Selangor", (0, 2, 4)),
    ("C20002", "Kedai Runcit Ah Seng", "MINI", "S", "KLANG", "Teoh Ah Seng", "+60 12-310 8846",
     "No. 5, Jalan Sungai Bertek, 41100 Klang, Selangor", (1, 4)),
    ("C20003", "FreshMart Supermarket Puchong", "MINI", "L", "SOUTH", "Grace Yap", "+60 3-8076 1120",
     "G-12, Jalan Puteri 1/2, Bandar Puteri, 47100 Puchong, Selangor", (0, 2, 4)),
    ("C20004", "Restoran Selera Kampung", "REST", "M", "SA", "Rahimah binti Daud", "+60 19-276 4410",
     "No. 3, Jalan Kristal K7/K, Seksyen 7, 40000 Shah Alam, Selangor", (1, 4)),
    ("C20005", "Grand Puteri Hotel Kuala Lumpur", "HOTEL", "L", "PJ_KL", "Rajesh Pillai (Purchasing)", "+60 3-2142 8800",
     "No. 88, Jalan Sultan Ismail, 50250 Kuala Lumpur", (0, 2, 4)),
    ("C20006", "Kopitiam Lim Brothers", "CAFE", "S", "PJ_KL", "Lim Wei Jie", "+60 16-332 7095",
     "No. 21, Jalan SS 2/64, SS 2, 47300 Petaling Jaya, Selangor", (1, 3, 5)),
    ("C20007", "Kantin Sekolah Seri Damai", "CANTEEN", "M", "KLANG", "Puan Zaleha", "+60 13-334 2718",
     "Jalan Seri Damai 2, Taman Seri Damai, 41200 Klang, Selangor", (0, 3)),
    ("C20008", "Pasaraya Mega Jimat Rawang", "MINI", "L", "OUT", "Faridah binti Salleh", "+60 3-6092 4416",
     "Lot 2, Jalan Bandar Rawang 4, 48000 Rawang, Selangor", (1, 4)),
    ("C20009", "Restoran Nasi Kandar Maju", "REST", "L", "PJ_KL", "Mohamed Ismail", "+60 12-655 0931",
     "No. 102, Jalan Tuanku Abdul Rahman, 50100 Kuala Lumpur", (0, 2, 4)),
    ("C20010", "Bayu Catering Services", "CATER", "L", "SOUTH", "Azlan bin Mahmud", "+60 17-882 3104",
     "No. 9, Jalan P10/21, Seksyen 10, 43650 Bandar Baru Bangi, Selangor", (0, 3)),
    ("C20011", "Kedai Runcit Sri Murugan", "MINI", "S", "KLANG", "Murugan a/l Arumugam", "+60 12-209 5527",
     "No. 47, Jalan Tengku Kelana, 41000 Klang, Selangor", (2, 5)),
    ("C20012", "Cafe Daun Pandan", "CAFE", "M", "PJ_KL", "Sharifah Nadia", "+60 11-2345 6182",
     "No. 6, Jalan 17/45, Seksyen 17, 46400 Petaling Jaya, Selangor", (1, 4)),
    ("C20013", "The Orchid Serviced Suites Cyberjaya", "HOTEL", "M", "SOUTH", "Nicholas Chan", "+60 3-8320 5500",
     "Persiaran Multimedia, Cyber 7, 63000 Cyberjaya, Selangor", (1, 4)),
    ("C20014", "Restoran Hock Kee Seafood", "REST", "M", "KLANG", "Ong Hock Kee", "+60 12-386 2240",
     "No. 1, Jalan Pelabuhan Utara, 42000 Port Klang, Selangor", (0, 3)),
    ("C20015", "Pasar Mini Keluarga Subang", "MINI", "M", "SA", "Norhayati binti Ali", "+60 3-5631 9047",
     "No. 33, Jalan USJ 9/5Q, 47620 Subang Jaya, Selangor", (1, 3, 5)),
    ("C20016", "D'Selera Food Court Putrajaya", "CANTEEN", "M", "SOUTH", "Khairul Anuar", "+60 19-301 6623",
     "Presint 3, 62675 Putrajaya", (0, 2, 4)),
    ("C20017", "Sunrise Bakery & Cafe", "CAFE", "M", "SA", "Jessica Teh", "+60 3-5524 6610",
     "No. 12, Jalan Setia Prima S U13/S, Setia Alam, 40170 Shah Alam, Selangor", (0, 3)),
    ("C20018", "Kedai Serbaneka Bintang", "MINI", "S", "SOUTH", "Azizah binti Yaakob", "+60 13-610 2287",
     "No. 8, Jalan Kenari 5, Bandar Puchong Jaya, 47100 Puchong, Selangor", (2,)),
    ("C20019", "Restoran Thai Lemongrass", "REST", "S", "PJ_KL", "Somchai Wong", "+60 17-218 9934",
     "No. 15, Jalan Telawi 3, Bangsar Baru, 59100 Kuala Lumpur", (1, 4)),
    ("C20020", "Seremban Fresh Grocer", "MINI", "M", "OUT", "Chan Kah Mun", "+60 6-762 1158",
     "No. 77, Jalan Dato Bandar Tunggal, 70000 Seremban, Negeri Sembilan", (2, 5)),
    ("C20021", "Hotel Seri Kenanga Klang", "HOTEL", "S", "KLANG", "Vincent Raj", "+60 3-3371 8022",
     "No. 2, Jalan Meru, 41050 Klang, Selangor", (2,)),
    ("C20022", "Warung Pak Din", "REST", "S", "SA", "Kamarudin bin Hamzah", "+60 19-664 7712",
     "Gerai 4, Medan Selera Seksyen 13, 40100 Shah Alam, Selangor", (0, 3)),
    ("C20023", "Kantin Kilang Electronica Sdn Bhd", "CANTEEN", "L", "SA", "Suresh Kumar", "+60 3-5192 4400",
     "Lot 5, Jalan Hasil 16/1, Seksyen 16, 40200 Shah Alam, Selangor", (0, 2, 4)),
    ("C20024", "Mini Market 7 Hari", "MINI", "M", "PJ_KL", "Hafizah binti Rosli", "+60 3-7865 3301",
     "No. 40, Jalan PJU 1/41, Dataran Prima, 47301 Petaling Jaya, Selangor", (1, 3, 5)),
]

AFFINITY = {
    "MINI": {"bev": 1.2, "dairy": 1.0, "frozen": 0.6, "rice": 1.2, "dry": 1.2, "oil": 1.0, "sauce": 1.0,
             "snack": 1.4, "canned": 1.2, "household": 1.3},
    "REST": {"bev": 0.8, "dairy": 0.8, "frozen": 1.2, "rice": 1.6, "dry": 1.2, "oil": 1.6, "sauce": 1.5,
             "snack": 0.1, "canned": 0.5, "household": 0.3},
    "HOTEL": {"bev": 1.3, "dairy": 1.6, "frozen": 1.3, "rice": 1.0, "dry": 1.0, "oil": 1.0, "sauce": 0.8,
              "snack": 0.2, "canned": 0.4, "household": 0.9},
    "CAFE": {"bev": 1.6, "dairy": 1.6, "frozen": 1.0, "rice": 0.3, "dry": 1.1, "oil": 0.5, "sauce": 0.6,
             "snack": 0.4, "canned": 0.2, "household": 0.3},
    "CANTEEN": {"bev": 1.3, "dairy": 0.5, "frozen": 1.0, "rice": 1.6, "dry": 1.0, "oil": 1.3, "sauce": 1.0,
                "snack": 1.0, "canned": 0.6, "household": 0.3},
    "CATER": {"bev": 1.2, "dairy": 0.8, "frozen": 1.2, "rice": 1.8, "dry": 1.2, "oil": 1.6, "sauce": 1.4,
              "snack": 0.2, "canned": 0.8, "household": 0.4},
}
SIZES = {"L": (1.6, (8, 14), 0.95), "M": (1.0, (5, 9), 0.9), "S": (0.55, (3, 6), 0.85)}

# Delivery routes: carrier, vehicle, driver, phone, sealed (third-party trucks are sealed)
ROUTES = {
    "SA": ("Own fleet", "BPK 4519", "Muthu a/l Raman", "+60 16-702 3381", False),
    "KLANG": ("Own fleet", "BMN 7283", "Rosli bin Ahmad", "+60 12-338 4172", False),
    "PJ_KL": ("Own fleet", "WVD 2806", "Chong Kar Wai", "+60 17-845 2290", False),
    "SOUTH": ("Own fleet", "BQA 1162", "Azman bin Yusof", "+60 13-291 6654", False),
    "OUT": ("Laju Logistik Sdn Bhd", "BRT 3307", "Gopal a/l Subramaniam", "+60 12-771 0458", True),
}

# username, display name, role
STAFF = [
    ("siti.hajar", "Siti Hajar binti Zainal", "SUPERVISOR"),   # purchasing & order desk
    ("tan.weiming", "Tan Wei Ming", "SUPERVISOR"),            # warehouse supervisor: posts documents
    ("nurul.aina", "Nurul Aina binti Kassim", "CLERK"),        # receiving & putaway
    ("ravi.kumar", "Ravi Kumar a/l Selvam", "CLERK"),          # picker
    ("hafiz.rahman", "Mohd Hafiz bin Abdul Rahman", "CLERK"),  # picker
    ("lim.kokhoe", "Lim Kok Hoe", "CLERK"),                    # loading
]
OFFICE, SUPERVISOR, RECEIVER, PICKERS, LOADER = "siti.hajar", "tan.weiming", "nurul.aina", ("ravi.kumar", "hafiz.rahman"), "lim.kokhoe"

SO_REMARKS = ["Deliver before 10am", "Call before delivery", "Back lane loading bay", "Please bring invoice copy",
              "Kitchen entrance, ask for the chef", "Loading dock B", "Urgent - weekend promotion"]
PO_REMARKS = ["Year-end promotion stock", "Please deliver on pallets, max height 1.5m", "Confirm delivery slot with receiving",
              "Price as per quotation Q-2026-118"]
DAMAGE_REMARKS = ["Carton crushed during picking", "Leaking bottle found in bin", "Dented tins - not saleable",
                  "Torn packets found at count", "Dropped from forklift"]


@dataclass
class Item:
    sku: str
    name: str
    category: str
    key: str
    base: str
    per_ctn: int | None
    per_plt: int
    zone: str
    shelf: int | None
    cost: Decimal
    demand: float
    supplier: str
    id: str = ""
    daily_base: float = 0.0  # average base units sold per working day (from the generated orders)

    @property
    def order_uom(self) -> str:
        return "CTN" if self.per_ctn else self.base

    @property
    def order_factor(self) -> int:
        return self.per_ctn or 1


@dataclass
class Supplier:
    key: str
    code: str
    name: str
    terms: int
    lead: int
    days: tuple
    barcode: str
    id: str = ""


@dataclass
class Customer:
    code: str
    name: str
    kind: str
    size: str
    route: str
    days: tuple
    id: str = ""


@dataclass
class OrderPlan:
    day: REAL_DATE
    customer: Customer
    lines: list  # (item, uom code, qty)
    remark: str | None


@dataclass
class OpenPo:
    id: str
    doc_no: str
    supplier: Supplier
    due: REAL_DATE
    close_on: REAL_DATE | None = None


@dataclass
class OpenSo:
    id: str
    customer: Customer
    day: REAL_DATE
    staged: bool = False
    short: bool = False


@dataclass
class Sim:
    items: dict[str, Item] = field(default_factory=dict)
    suppliers: dict[str, Supplier] = field(default_factory=dict)
    customers: list[Customer] = field(default_factory=list)
    uoms: dict[str, str] = field(default_factory=dict)
    users: dict[str, str] = field(default_factory=dict)
    bins: dict[str, list[str]] = field(default_factory=dict)
    docks_in: list[str] = field(default_factory=list)
    docks_out: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    pos: dict[str, OpenPo] = field(default_factory=dict)
    sos: dict[str, OpenSo] = field(default_factory=dict)
    payables: list = field(default_factory=list)  # (grn id, supplier key, due date)
    wh: str = ""
    qa_bins: list[str] = field(default_factory=list)
    assets: dict[str, str] = field(default_factory=dict)  # asset code -> type id
    out_assets: dict = field(default_factory=lambda: defaultdict(float))  # (customer code, asset code) -> outstanding
    shipped: list = field(default_factory=list)  # (day, so id, customer, shipment lines)
    portal_user: str = ""
    hamper: Item | None = None
    recall_done: bool = False
    repack_done: bool = False
    stats: dict[str, int] = field(default_factory=lambda: defaultdict(int))


# ---------------------------------------------------------------- API access


class ApiError(Exception):
    pass


class Api:
    def __init__(self, tenant_id: uuid.UUID):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app)
        self.tenant_id = tenant_id
        self.user_ids: dict[str, uuid.UUID] = {}

    def call(self, user: str, method: str, path: str, body=None, ok: bool = True, idem: bool = False, **params):
        from app.core.security import create_access_token

        token = create_access_token(self.user_ids[user], self.tenant_id)
        headers = {"Authorization": f"Bearer {token}"}
        if idem:  # the PDA sends an Idempotency-Key with every scan, so a resend after a lost response is safe
            headers["Idempotency-Key"] = str(uuid.uuid4())
        response = self.client.request(method, "/api/v1" + path, json=body, params=params or None, headers=headers)
        if not response.is_success:
            if ok:
                raise ApiError(f"{method} {path} -> {response.status_code} {response.text[:400]}")
            return None
        return response.json() if response.content else {}

    def post(self, user: str, path: str, body=None, ok: bool = True, idem: bool = False):
        return self.call(user, "POST", path, body, ok, idem)

    def get(self, user: str, path: str, **params):
        return self.call(user, "GET", path, **params)


def q(value) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.0001")).normalize())


def ean13(prefix: str, number: int) -> str:
    body = f"{prefix}{number:05d}"[:12]
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


# ---------------------------------------------------------------- wipe


def wipe(tenant_id: uuid.UUID) -> None:
    from app.core.db import SessionLocal

    statements = [
        "UPDATE [user] SET partner_id = NULL WHERE tenant_id = :t",
        # Saved carts point at deleted customers and items
        "DELETE p FROM user_preference p JOIN [user] u ON u.id = p.user_id WHERE u.tenant_id = :t",
        "DELETE FROM label_profile WHERE tenant_id = :t",
        "DELETE m FROM assistant_message m JOIN assistant_conversation c ON c.id = m.conversation_id WHERE c.tenant_id = :t",
        "DELETE FROM assistant_conversation WHERE tenant_id = :t",
        "DELETE l FROM integration_log l JOIN integration_job j ON j.id = l.job_id WHERE j.tenant_id = :t",
        "DELETE FROM integration_job WHERE tenant_id = :t",
        "DELETE FROM integration_event WHERE tenant_id = :t",
        "DELETE FROM integration_connector WHERE tenant_id = :t",
        "DELETE FROM document_attachment WHERE tenant_id = :t",
        "DELETE FROM count_entry WHERE tenant_id = :t",
        "DELETE FROM document_location WHERE tenant_id = :t",
        "DELETE s FROM shipment_info s JOIN document_header h ON h.id = s.document_id WHERE h.tenant_id = :t",
        "DELETE FROM stock_ledger WHERE tenant_id = :t",
        "DELETE FROM stock_balance WHERE tenant_id = :t",
        "DELETE FROM returnable_asset_txn WHERE tenant_id = :t",
        "UPDATE document_line SET ref_line_id = NULL WHERE tenant_id = :t",
        "DELETE FROM document_line WHERE tenant_id = :t",
        "UPDATE document_header SET ref_document_id = NULL WHERE tenant_id = :t",
        "DELETE FROM document_header WHERE tenant_id = :t",
        "DELETE FROM recipe_line WHERE tenant_id = :t",
        "DELETE FROM recipe WHERE tenant_id = :t",
        "DELETE FROM item_barcode WHERE tenant_id = :t",
        "DELETE FROM item_uom_conversion WHERE tenant_id = :t",
        "DELETE FROM item WHERE tenant_id = :t",
        "DELETE FROM returnable_asset_type WHERE tenant_id = :t",
        "DELETE FROM business_partner WHERE tenant_id = :t",
        "UPDATE location SET parent_id = NULL WHERE tenant_id = :t",
        "DELETE FROM location WHERE tenant_id = :t",
        "DELETE FROM idempotency_key",
        "DELETE FROM audit_log WHERE tenant_id = :t",
        # Leftovers of automated tests: reason codes named "r" with generated codes
        "DELETE FROM reason_code WHERE tenant_id = :t AND name = N'r'",
        "UPDATE doc_number_rule SET current_period = N'', current_seq = 0 WHERE tenant_id = :t",
    ]
    with SessionLocal() as db:
        for sql in statements:
            db.execute(text(sql), {"t": tenant_id})
        db.commit()
    print("Wiped master and business data")


# ---------------------------------------------------------------- master data


def ensure_uoms_and_users(sim: Sim, api: Api, tenant_id: uuid.UUID, password: str) -> None:
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.core.security import hash_password
    from app.models.item import Uom
    from app.models.reason_code import ReasonCode
    from app.models.user import Role, User, UserRole

    with SessionLocal() as db:
        existing = {u.code: u for u in db.scalars(select(Uom).where(Uom.tenant_id == tenant_id))}
        for code, name in UOMS:
            if code not in existing:
                existing[code] = Uom(tenant_id=tenant_id, code=code, name=name)
                db.add(existing[code])
        db.flush()
        sim.uoms = {code: str(u.id) for code, u in existing.items()}

        roles = {r.code: r for r in db.scalars(select(Role).where(Role.tenant_id == tenant_id))}
        admin = db.scalars(select(User).where(User.tenant_id == tenant_id, User.username == "admin")).first()
        if admin is None:
            raise SystemExit("No admin user: run python -m scripts.seed first")
        api.user_ids["admin"] = admin.id
        for username, display_name, role_code in STAFF:
            user = db.scalars(select(User).where(User.tenant_id == tenant_id, User.username == username)).first()
            if user is None:
                user = User(tenant_id=tenant_id, username=username, display_name=display_name,
                            password_hash=hash_password(password))
                db.add(user)
                db.flush()
                db.add(UserRole(user_id=user.id, role_id=roles[role_code].id))
            api.user_ids[username] = user.id

        sim.reasons = {
            r.code: str(r.id)
            for r in db.scalars(select(ReasonCode).where(ReasonCode.tenant_id == tenant_id, ReasonCode.category == "ADJUST"))
        }
        db.commit()


def create_locations(sim: Sim, api: Api) -> None:
    def loc(code, name, kind, parent=None, pickable=False):
        body = {"code": code, "name": name, "location_type": kind, "is_pickable": pickable}
        if parent:
            body["parent_id"] = parent
        return api.post("admin", "/locations", body)["id"]

    wh = sim.wh = loc("SA-DC", "Shah Alam Distribution Centre", "WAREHOUSE")
    for n in (1, 2, 3):
        sim.docks_in.append(loc(f"RCV-0{n}", f"Receiving dock {n}", "DOCK", wh))
    for n in (1, 2, 3):
        sim.docks_out.append(loc(f"DSP-0{n}", f"Dispatch staging lane {n}", "DOCK", wh))

    zones = [("AMB", "Ambient racking", "A", 4, 8, 4), ("CHL", "Chiller 2-8 °C", "C", 2, 5, 3), ("FRZ", "Freezer -18 °C", "F", 1, 4, 3)]
    for zone_code, zone_name, letter, aisles, racks, levels in zones:
        zone = loc(zone_code, zone_name, "ZONE", wh)
        sim.bins[zone_code] = []
        for a in range(1, aisles + 1):
            aisle_code = f"{letter}{a:02d}"
            aisle = loc(aisle_code, f"{zone_name} aisle {a:02d}", "AISLE", zone)
            for r in range(1, racks + 1):
                rack_code = f"{aisle_code}-{r:02d}"
                rack = loc(rack_code, f"Aisle {aisle_code} rack {r:02d}", "RACK", aisle)
                for lv in range(1, levels + 1):
                    sim.bins[zone_code].append(
                        loc(f"{rack_code}-{lv}", f"Aisle {aisle_code} rack {r:02d} level {lv}", "BIN", rack, pickable=True)
                    )
    print(f"Created warehouse SA-DC: {sum(len(b) for b in sim.bins.values())} bins, 6 docks")


def create_partners(sim: Sim, api: Api) -> None:
    for key, code, name, contact, phone, address, terms, lead, days, barcode in SUPPLIERS:
        supplier = Supplier(key, code, name, terms, lead, days, barcode)
        supplier.id = api.post("admin", "/business-partners", {
            "code": code, "name": name, "partner_type": "supplier", "contact_name": contact,
            "contact_phone": phone, "address": address, "credit_terms_days": terms,
        })["id"]
        sim.suppliers[key] = supplier
    for code, name, kind, size, route, contact, phone, address, days in CUSTOMERS:
        customer = Customer(code, name, kind, size, route, days)
        customer.id = api.post("admin", "/business-partners", {
            "code": code, "name": name, "partner_type": "customer", "contact_name": contact,
            "contact_phone": phone, "address": address,
        })["id"]
        sim.customers.append(customer)
    print(f"Created {len(sim.suppliers)} suppliers, {len(sim.customers)} customers")


def create_items(sim: Sim, api: Api) -> None:
    seq = defaultdict(int)
    for sku, name, category, key, base, per_ctn, per_plt, zone, shelf, cost, demand, supplier in ITEMS:
        item = Item(sku, name, category, key, base, per_ctn, per_plt, zone, shelf, Decimal(cost), demand, supplier)
        seq[supplier] += 1
        packings = []
        if per_ctn:
            packings.append({"uom_id": sim.uoms["CTN"], "factor": str(per_ctn)})
        packings.append({"uom_id": sim.uoms["PLT"], "factor": str(per_plt)})
        item.id = api.post("admin", "/items", {
            "sku_code": sku, "name": name, "category": category, "base_uom_id": sim.uoms[base],
            "barcode": ean13(sim.suppliers[supplier].barcode, seq[supplier]),
            "is_batch_managed": shelf is not None, "is_expiry_managed": shelf is not None,
            "shelf_life_days": shelf, "packings": packings,
        })["id"]
        sim.items[sku] = item
    sku, name, category, base, per_ctn, supplier = DISCONTINUED
    seq[supplier] += 1
    api.post("admin", "/items", {
        "sku_code": sku, "name": name, "category": category, "base_uom_id": sim.uoms[base],
        "barcode": ean13(sim.suppliers[supplier].barcode, seq[supplier]), "is_batch_managed": True,
        "is_expiry_managed": True, "shelf_life_days": 180, "is_active": False,
        "packings": [{"uom_id": sim.uoms["CTN"], "factor": str(per_ctn)}],
    })
    print(f"Created {len(sim.items) + 1} items")


def set_min_stock(sim: Sim, api: Api) -> None:
    """Low-stock alarm at about four days of sales"""
    for item in sim.items.values():
        api.call("admin", "PUT", f"/items/{item.id}", {
            "min_stock_qty": q(math.ceil(item.daily_base * 4 / item.order_factor) * item.order_factor),
        })


# ---------------------------------------------------------------- demand plan


def working_days(start: REAL_DATE, end: REAL_DATE) -> list[REAL_DATE]:
    days, day = [], start
    while day <= end:
        if day.weekday() != 6:  # closed on Sundays
            days.append(day)
        day += _dt.timedelta(days=1)
    return days


def plan_orders(sim: Sim, rng: random.Random, days: list[REAL_DATE]) -> list[OrderPlan]:
    plans = []
    items = list(sim.items.values())
    for day in days:
        for customer in sim.customers:
            factor, (low, high), chance = SIZES[customer.size]
            if day.weekday() not in customer.days or rng.random() > chance:
                continue
            affinity = AFFINITY[customer.kind]
            weights = [item.demand ** 0.7 * affinity[item.key] for item in items]
            chosen: list[Item] = []
            for _ in range(rng.randint(low, high)):
                pick = rng.choices(items, weights)[0]
                if pick not in chosen:
                    chosen.append(pick)
            lines = []
            for item in chosen:
                qty = max(1, round(math.sqrt(item.demand) * factor * rng.uniform(0.5, 1.5)))
                if item.per_ctn and customer.size == "S" and item.per_ctn >= 12 and rng.random() < 0.3:
                    lines.append((item, item.base, qty * rng.choice((3, 4, 6))))  # small shops buy loose units
                else:
                    lines.append((item, item.order_uom, qty))
            remark = rng.choice(SO_REMARKS) if rng.random() < 0.15 else None
            plans.append(OrderPlan(day, customer, lines, remark))
    for item in items:
        sold = sum(qty * (item.order_factor if uom == item.order_uom else 1)
                   for plan in plans for it, uom, qty in plan.lines if it is item)
        item.daily_base = sold / max(len(days), 1)
    return plans


# ---------------------------------------------------------------- database reads


def db_rows(sql: str, **params):
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        return db.execute(text(sql), params).all()


def stock_position(sim: Sim, tenant_id) -> dict[str, float]:
    """Available stock plus what is still due on open purchase orders, in base units, per item id"""
    position: dict[str, float] = defaultdict(float)
    for item_id, qty in db_rows(
        "SELECT item_id, SUM(qty_on_hand - qty_allocated) FROM stock_balance WHERE tenant_id = :t GROUP BY item_id", t=tenant_id
    ):
        position[str(item_id).lower()] += float(qty)
    factors = {}
    for item in sim.items.values():
        factors[(item.id, sim.uoms[item.base])] = 1
        factors[(item.id, sim.uoms["PLT"])] = item.per_plt
        if item.per_ctn:
            factors[(item.id, sim.uoms["CTN"])] = item.per_ctn
    for item_id, uom_id, planned, actual in db_rows(
        "SELECT l.item_id, l.uom_id, l.qty_planned, l.qty_actual FROM document_line l JOIN document_header h ON h.id = l.document_id "
        "WHERE h.tenant_id = :t AND h.doc_type = 'PO' AND h.status IN ('DRAFT', 'CONFIRMED', 'PARTIALLY_RECEIVED')", t=tenant_id
    ):
        key = (str(item_id).lower(), str(uom_id).lower())
        position[key[0]] += max(float(planned) - float(actual), 0) * factors.get(key, 1)
    return position


# ---------------------------------------------------------------- daily work


def create_po(sim: Sim, api: Api, rng: random.Random, supplier: Supplier, day: REAL_DATE, lines: list, confirm: bool,
              price_factor) -> None:
    expected = day + _dt.timedelta(days=supplier.lead)
    if expected.weekday() == 6:
        expected += _dt.timedelta(days=1)
    body = {
        "partner_id": supplier.id, "expected_date": expected.isoformat(),
        "remark": rng.choice(PO_REMARKS) if rng.random() < 0.12 else None,
        "lines": [
            {"item_id": item.id, "uom_id": sim.uoms[item.order_uom], "qty": q(qty),
             "unit_price": q((item.cost * item.order_factor * price_factor(item, day)).quantize(Decimal("0.01"), ROUND_HALF_UP))}
            for item, qty in lines
        ],
    }
    po = api.post(OFFICE, "/purchase-orders", body)
    sim.stats["PO"] += 1
    if confirm:
        api.post(SUPERVISOR, f"/purchase-orders/{po['id']}/confirm")
        late = 1 if rng.random() < 0.12 else 0
        due = expected + _dt.timedelta(days=late)
        if due.weekday() == 6:
            due += _dt.timedelta(days=1)
        sim.pos[po["id"]] = OpenPo(po["id"], po["doc_no"], supplier, due)


def purchasing(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE, tenant_id, price_factor, today: REAL_DATE) -> None:
    due_suppliers = [s for s in sim.suppliers.values() if day.weekday() in s.days]
    if not due_suppliers or not clock.at(day, 11.0):
        return
    position = stock_position(sim, tenant_id)
    for n, supplier in enumerate(due_suppliers):
        if not clock.at(day, 11.0 + n * 0.25):
            return
        review = 7 / len(supplier.days)
        lines = []
        for item in sim.items.values():
            if item.supplier != supplier.key or item.daily_base <= 0:
                continue
            cover = supplier.lead + review + (2 if (item.shelf or 999) < 30 else 4)
            if item.shelf and item.shelf < 30:
                cover = min(cover, item.shelf * 0.5)
            target = item.daily_base * cover
            have = position.get(item.id.lower(), 0.0)
            if have >= target * 0.85:
                continue
            qty = math.ceil((target - have) / item.order_factor)
            minimum = 5 if item.per_ctn else 20
            lines.append((item, max(qty, minimum)))
        if lines:
            create_po(sim, api, rng, supplier, day, lines, confirm=not (day == today and rng.random() < 0.4),
                      price_factor=price_factor)


def batch_for(item: Item, day: REAL_DATE, rng) -> tuple[str | None, str | None]:
    if not item.shelf:
        return None, None
    age = rng.randint(1, max(2, min(30, item.shelf // 8)))
    made = day - _dt.timedelta(days=age)
    return f"{made:%y%m%d}{rng.choice('ABC')}", (made + _dt.timedelta(days=item.shelf)).isoformat()


def receiving(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE, tenant_id) -> None:
    hour = 8.75
    occupied = {str(r[0]).lower() for r in db_rows(
        "SELECT location_id FROM stock_balance WHERE tenant_id = :t AND qty_on_hand > 0", t=tenant_id)}
    by_id = {item.id.lower(): item for item in sim.items.values()}
    for po in sorted(list(sim.pos.values()), key=lambda p: p.due):
        if po.close_on and po.close_on <= day:
            if clock.at(day, 8.5) and api.post(SUPERVISOR, f"/purchase-orders/{po.id}/close", ok=False) is not None:
                del sim.pos[po.id]
            continue
        if po.due > day:
            continue
        hour += rng.uniform(0.3, 0.8)
        if not clock.at(day, hour):
            return
        lines = []
        short = False
        for line_id, item_id, planned, actual in db_rows(
            "SELECT id, item_id, qty_planned, qty_actual FROM document_line WHERE document_id = :d ORDER BY line_no", d=po.id
        ):
            remaining = float(planned) - float(actual)
            if remaining <= 0:
                continue
            item = by_id[str(item_id).lower()]
            qty = remaining
            if po.close_on is None and remaining >= 4 and rng.random() < 0.07:
                qty = max(1, math.floor(remaining * rng.uniform(0.6, 0.92)))
                short = True
            batch, expiry = batch_for(item, day, rng)
            lines.append({"po_line_id": str(line_id), "qty": q(qty), "batch_no": batch, "expiry_date": expiry})
        if not lines:
            continue
        dock = sim.docks_in[sim.stats["GRN"] % len(sim.docks_in)]
        grn = api.post(RECEIVER, "/grns", {"po_id": po.id, "location_id": dock, "lines": lines}, idem=True)
        sim.stats["GRN"] += 1
        if not clock.at(day, hour + 0.3):
            return
        api.post(SUPERVISOR, f"/grns/{grn['id']}/post")
        sim.payables.append((grn["id"], po.supplier.key, day + _dt.timedelta(days=po.supplier.terms)))
        if short:
            safely(attach, api, RECEIVER, grn["id"], f"Short delivery on {po.doc_no}: supplier DO shows fewer cartons", rng)
            if rng.random() < 0.5:
                po.due = day + _dt.timedelta(days=rng.randint(2, 3))
                if po.due.weekday() == 6:
                    po.due += _dt.timedelta(days=1)
            else:
                po.close_on = day + _dt.timedelta(days=3)  # supplier cannot supply the rest: closed short later
        else:
            del sim.pos[po.id]

        # Putaway sheet created by posting: put every line into its suggested bin, or the next free bin of its zone
        sheet = db_rows(
            "SELECT id FROM document_header WHERE tenant_id = :t AND doc_type = 'PUTAWAY' AND ref_document_id = :g AND status = 'TO_PUT_AWAY'",
            t=tenant_id, g=grn["id"],
        )
        if not sheet:
            continue
        sheet_id = str(sheet[0][0])
        put_hour = hour + 0.6
        complete = True
        for line_id, item_id, qty, suggested in db_rows(
            "SELECT id, item_id, qty_planned, to_location_id FROM document_line WHERE document_id = :d ORDER BY line_no", d=sheet_id
        ):
            put_hour += rng.uniform(0.04, 0.09)
            if not clock.at(day, put_hour):
                complete = False
                break
            item = by_id[str(item_id).lower()]
            target = str(suggested).lower() if suggested else None
            if target is None:
                free = [b for b in sim.bins[item.zone] if b.lower() not in occupied]
                target = (free or sim.bins[item.zone])[0]
            occupied.add(target.lower())
            api.post(RECEIVER, f"/putaways/{sheet_id}/lines/{line_id}/put", {"to_location_id": target, "qty": q(qty)}, idem=True)
        if complete and clock.at(day, put_hour + 0.05):
            api.post(RECEIVER, f"/putaways/{sheet_id}/post")
            sim.stats["PUTAWAY"] += 1
        hour = max(hour, put_hour - 0.4)


def order_intake(sim: Sim, api: Api, clock: Clock, plans: list[OrderPlan], day: REAL_DATE, next_day: REAL_DATE) -> None:
    hour = 8.0
    for plan in plans:
        hour += 0.12
        if not clock.at(day, hour):
            return
        body = {
            "partner_id": plan.customer.id, "expected_date": next_day.isoformat(), "remark": plan.remark,
            "lines": [{"item_id": item.id, "uom_id": sim.uoms[uom], "qty": q(qty)} for item, uom, qty in plan.lines],
        }
        if plan.customer.code == PORTAL_CUSTOMER and sim.portal_user:
            # This customer orders through the shopping cart; the order desk confirms it
            so = api.post(sim.portal_user, "/cart/orders", {k: v for k, v in body.items() if k != "partner_id"})
            if not clock.at(day, hour + 0.3):
                return
        else:
            so = api.post(OFFICE, "/sales-orders", body)
        api.post(OFFICE, f"/sales-orders/{so['id']}/confirm")
        sim.sos[so["id"]] = OpenSo(so["id"], plan.customer, day)
        sim.stats["SO"] += 1


def picking(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE, days: list[REAL_DATE]) -> None:
    hour = 13.5
    free = {picker: 13.5 for picker in PICKERS}
    route_lane = {route: sim.docks_out[n % len(sim.docks_out)] for n, route in enumerate(sorted(ROUTES))}
    for so in sorted(sim.sos.values(), key=lambda s: s.day):
        if so.staged and not so.short:
            continue
        age = sum(1 for d in days if so.day < d <= day)
        if so.short and age >= 3:
            # The customer does not wait any longer for the backorder: close what is left (once nothing is staged)
            if not so.staged and clock.at(day, hour) and (
                api.post(SUPERVISOR, f"/sales-orders/{so.id}/cancel", ok=False) is not None
                or api.post(SUPERVISOR, f"/sales-orders/{so.id}/close", ok=False) is not None
            ):
                del sim.sos[so.id]
            continue
        hour += rng.uniform(0.08, 0.2)
        if not clock.at(day, hour):
            return
        result = api.post(SUPERVISOR, f"/sales-orders/{so.id}/allocate",
                          {"staging_location_id": route_lane[so.customer.route]}, ok=False)
        if result is None:
            so.short = True
            continue
        so.short = bool(result["shortages"])
        pick = result["pick"]
        picker = min(PICKERS, key=lambda p: free[p])
        pick_hour = max(hour, free[picker])
        done = True
        for line in pick["lines"]:
            pick_hour += rng.uniform(0.02, 0.05)
            if not clock.at(day, pick_hour):
                done = False
                break
            api.post(picker, f"/picks/{pick['id']}/lines/{line['id']}/confirm", {"qty": line["qty_planned"]}, idem=True)
        if not done or not clock.at(day, pick_hour + 0.05):
            return
        api.post(SUPERVISOR, f"/picks/{pick['id']}/post")
        free[picker] = pick_hour + rng.uniform(0.03, 0.08)
        sim.stats["PICK"] += 1
        so.staged = True


def dispatch(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE) -> None:
    hour = 6.75
    seals = {}
    for so in sorted((s for s in sim.sos.values() if s.staged), key=lambda s: s.customer.route):
        hour += rng.uniform(0.05, 0.12)
        if not clock.at(day, hour):
            return
        carrier, vehicle, driver, phone, sealed = ROUTES[so.customer.route]
        if sealed and so.customer.route not in seals:
            seals[so.customer.route] = f"LL{rng.randint(100000, 999999)}"
        ship = api.post(LOADER, "/shipments", {
            "so_id": so.id, "carrier": carrier, "vehicle_no": vehicle, "driver_name": driver,
            "driver_phone": phone, "seal_no": seals.get(so.customer.route),
        }, ok=False)
        if ship is None:
            so.staged = False
            continue
        done = True
        for line in ship["lines"]:
            hour += rng.uniform(0.01, 0.025)
            if not clock.at(day, hour):
                done = False
                break
            api.post(LOADER, f"/shipments/{ship['id']}/lines/{line['id']}/check", {"qty": line["qty_actual"]}, idem=True)
        if not done or not clock.at(day, hour + 0.02):
            return
        api.post(SUPERVISOR, f"/shipments/{ship['id']}/post")
        sim.stats["DO"] += 1
        sim.shipped.append((day, so.id, so.customer, ship["lines"]))
        safely(returnable_assets, sim, api, rng, so, ship)
        if sealed:
            safely(attach, api, LOADER, ship["id"], f"{vehicle} loaded and sealed, seal {seals[so.customer.route]}", rng)
        so.staged = False
        status = api.get(SUPERVISOR, f"/sales-orders/{so.id}")["status"]
        if status in ("SHIPPED", "CLOSED"):
            del sim.sos[so.id]


def write_offs(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE, tenant_id) -> None:
    """Mondays: expired stock is written off. Some days: a damaged carton found while picking"""
    if day.weekday() == 0 and clock.at(day, 8.25):
        rows = db_rows(
            "SELECT b.item_id, b.location_id, b.batch_no, b.expiry_date, b.qty_on_hand - b.qty_allocated FROM stock_balance b "
            "JOIN location l ON l.id = b.location_id WHERE b.tenant_id = :t AND l.location_type = 'BIN' "
            "AND b.expiry_date < :d AND b.qty_on_hand - b.qty_allocated > 0", t=tenant_id, d=day,
        )
        if rows:
            by_id = all_items(sim)
            adj = api.post(SUPERVISOR, "/adjustments", {
                "reason_code_id": sim.reasons["EXPIRED"], "remark": "Weekly expiry check",
                "lines": [{"item_id": str(i), "uom_id": sim.uoms[by_id[str(i).lower()].base], "location_id": str(loc),
                           "qty": q(-float(qty)), "batch_no": b, "expiry_date": e.isoformat() if e else None}
                          for i, loc, b, e, qty in rows],
            })
            api.post(SUPERVISOR, f"/adjustments/{adj['id']}/post")
            sim.stats["ADJUST"] += 1
    if rng.random() < 0.1 and clock.at(day, 15.5):
        rows = db_rows(
            "SELECT b.item_id, b.location_id, b.batch_no, b.expiry_date FROM stock_balance b JOIN location l ON l.id = b.location_id "
            "WHERE b.tenant_id = :t AND l.location_type = 'BIN' AND b.qty_on_hand - b.qty_allocated >= 6", t=tenant_id,
        )
        if rows:
            item_id, loc, batch, expiry = rng.choice(rows)
            item = all_items(sim).get(str(item_id).lower())
            if item is None:
                return
            adj = api.post(SUPERVISOR, "/adjustments", {
                "reason_code_id": sim.reasons["DAMAGE"], "remark": rng.choice(DAMAGE_REMARKS),
                "lines": [{"item_id": item.id, "uom_id": sim.uoms[item.base], "location_id": str(loc),
                           "qty": q(-rng.randint(1, min(6, item.order_factor))), "batch_no": batch,
                           "expiry_date": expiry.isoformat() if expiry else None}],
            })
            api.post(SUPERVISOR, f"/adjustments/{adj['id']}/post")
            sim.stats["ADJUST"] += 1


def payments(sim: Sim, api: Api, clock: Clock, day: REAL_DATE, end: REAL_DATE) -> None:
    """Fridays: accounts pay what falls due within the week. Lautan Biru's last invoices are held over a price dispute"""
    if day.weekday() != 4 or not clock.at(day, 15.0):
        return
    for entry in list(sim.payables):
        grn_id, supplier, due = entry
        if due > day + _dt.timedelta(days=7):
            continue
        if supplier == "CAN" and due >= end - _dt.timedelta(days=24):
            continue
        api.post("admin", f"/payables/{grn_id}/settle", {"settled_on": day.isoformat()})
        sim.payables.remove(entry)


# ---------------------------------------------------------------- the other modules: every table gets realistic rows

FAILURES: list[str] = []


def safely(step, *args):
    """Optional side flows must not abort a long simulation: report the failure and carry on"""
    try:
        return step(*args)
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{step.__name__}: {exc}"[:500])
        print(f"  ! {step.__name__} skipped: {exc}"[:300], flush=True)
        return None


FEATURES_ON = ("RETURNS", "REPACK", "RETURNABLE_ASSET", "RECIPES")
ASSET_TYPES = [("CRT-MILK", "Plastic milk crate"), ("PLT-STD", "Wooden pallet 1200 x 1000"), ("CAGE-RL", "Roll cage")]
PORTAL_CUSTOMER = "C20001"
ERP_FIX_DAY_FRACTION = 0.45  # until then the ERP did not know customer C20024: its shipment events were refused
HAMPER_RECIPE = [("BEV-1006", 1), ("BEV-1007", 1), ("DRY-2007", 2), ("SNK-6001", 1), ("SNK-6007", 1), ("CAN-7001", 2)]
KIT_RECIPE = [("BEV-1006", 2), ("DRY-2008", 2), ("SNK-6002", 2), ("RIC-4005", 1)]


def gtin14(ean: str, indicator: str = "1") -> str:
    body = indicator + ean[:12]
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


def photo(caption: str, rng: random.Random) -> str:
    """A small JPEG standing in for a PDA photo: cartons on a pallet, with the PDA's caption and time stamp"""
    import base64
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 480), (rng.randint(150, 180), rng.randint(150, 170), rng.randint(140, 160)))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 380, 640, 480), fill=(95, 95, 100))
    draw.rectangle((140, 360, 500, 385), fill=(150, 110, 70))
    for row in range(3):
        for col in range(4):
            shade = rng.randint(165, 205)
            x, y = 150 + col * 87, 280 - row * 80
            draw.rectangle((x, y, x + 82, y + 76), fill=(shade, int(shade * 0.78), int(shade * 0.55)), outline=(90, 70, 40))
    draw.rectangle((0, 0, 640, 34), fill=(0, 0, 0))
    draw.text((10, 10), caption[:90], fill=(255, 255, 255))
    draw.text((470, 450), FakeDatetime.now().strftime("%Y-%m-%d %H:%M"), fill=(255, 210, 0))
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode()


def attach(api: Api, user: str, doc_id: str, caption: str, rng) -> None:
    api.post(user, f"/documents/{doc_id}/attachments", {"content_base64": photo(caption, rng), "caption": caption}, idem=True)


def all_items(sim: Sim) -> dict[str, Item]:
    found = {i.id.lower(): i for i in sim.items.values()}
    if sim.hamper:
        found[sim.hamper.id.lower()] = sim.hamper
    return found


def bin_balances(tenant_id, item_id: str, zone_bins: list[str] | None = None):
    """Available stock of an item in bins, first expiry first: (location, batch, expiry, available)"""
    rows = db_rows(
        "SELECT b.location_id, b.batch_no, b.expiry_date, b.qty_on_hand - b.qty_allocated FROM stock_balance b "
        "JOIN location l ON l.id = b.location_id WHERE b.tenant_id = :t AND b.item_id = :i AND l.location_type = 'BIN' "
        "AND b.qty_on_hand - b.qty_allocated > 0 ORDER BY CASE WHEN b.expiry_date IS NULL THEN 1 ELSE 0 END, b.expiry_date, l.code",
        t=tenant_id, i=item_id,
    )
    return [r for r in rows if zone_bins is None or str(r[0]).lower() in zone_bins]


def free_bin(sim: Sim, tenant_id, zone: str) -> str:
    occupied = {str(r[0]).lower() for r in db_rows(
        "SELECT location_id FROM stock_balance WHERE tenant_id = :t AND qty_on_hand > 0", t=tenant_id)}
    free = [b for b in sim.bins[zone] if b.lower() not in occupied]
    return (free or sim.bins[zone])[-1]


def home_bin(sim: Sim, tenant_id, item: Item) -> str:
    rows = db_rows(
        "SELECT TOP 1 b.location_id FROM stock_balance b JOIN location l ON l.id = b.location_id WHERE b.tenant_id = :t "
        "AND b.item_id = :i AND l.location_type = 'BIN' AND l.is_pickable = 1 ORDER BY b.qty_on_hand DESC", t=tenant_id, i=item.id)
    return str(rows[0][0]) if rows else free_bin(sim, tenant_id, item.zone)


def create_extra_master(sim: Sim, api: Api, tenant_id, password: str) -> None:
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.core.security import hash_password
    from app.models.item import ItemBarcode
    from app.models.reason_code import ReasonCode
    from app.models.user import Role, User, UserRole

    for code in FEATURES_ON:
        api.call("admin", "PUT", f"/features/{code}", {"enabled": True})

    # Quality hold area: recalled and returned goods wait here, out of the pick faces
    zone = api.post("admin", "/locations", {"code": "QAH", "name": "Quality hold & returns", "location_type": "ZONE",
                                            "parent_id": sim.wh})["id"]
    for n in range(1, 5):
        sim.qa_bins.append(api.post("admin", "/locations", {
            "code": f"QA-0{n}", "name": f"Quality hold bay {n}", "location_type": "BIN", "parent_id": zone, "is_pickable": False,
        })["id"])

    for body in (
        {"name": "Bin label 75 x 50 (Zebra roll)", "purpose": "LOCATION", "media": "ROLL", "label_width_mm": 75,
         "label_height_mm": 50, "fields": ["code", "path"], "barcode_type": "CODE128", "font_size": 14, "is_default": True},
        {"name": "Shelf-edge item label A4 3 x 8", "purpose": "ITEM", "media": "SHEET", "label_width_mm": 70,
         "label_height_mm": 37, "columns": 3, "rows": 8, "margin_top_mm": 0.5, "fields": ["name", "sku", "barcode_text"],
         "barcode_type": "CODE128", "font_size": 8, "is_default": True},
        {"name": "Pallet / carton label 100 x 150", "purpose": "STOCK", "media": "ROLL", "label_width_mm": 100,
         "label_height_mm": 150, "fields": ["name", "sku", "batch", "expiry", "qty", "source"], "barcode_type": "QR",
         "font_size": 11, "is_default": True},
    ):
        api.post("admin", "/label-profiles", body)

    for code, name in ASSET_TYPES:
        sim.assets[code] = api.post(SUPERVISOR, "/returnable-assets/types", {"code": code, "name": name})["id"]

    api.post("admin", "/integration/connectors", {
        "code": "ERP", "name": "Finance ERP (stock & invoicing)", "endpoint_url": "https://erp.example.com/api/wms/events",
        "event_types": ["grn.posted", "shipment.posted", "adjustment.posted", "return_in.posted", "return_out.posted",
                        "purchase_order.confirmed", "sales_order.cancelled", "cycle_count.posted"],
        "extra_headers": {"X-Api-Key": "erp-demo-" + uuid.uuid4().hex[:16]}, "timeout_seconds": 15, "max_attempts": 5,
    })

    hamper = Item("HMP-9001", "Festive Goodies Hamper", "Gift Hampers", "gift", "BOX", None, 60, "AMB", None,
                  Decimal("0"), 0, "")
    hamper.id = api.post("admin", "/items", {
        "sku_code": hamper.sku, "name": hamper.name, "category": hamper.category, "base_uom_id": sim.uoms["BOX"],
        "barcode": ean13("9556199", 1), "packings": [{"uom_id": sim.uoms["PLT"], "factor": "60"}],
    })["id"]
    sim.hamper = hamper
    kit_id = api.post("admin", "/items", {
        "sku_code": "KIT-9002", "name": "Kopitiam Breakfast Starter Kit", "category": "Gift Hampers",
        "base_uom_id": sim.uoms["BOX"], "barcode": ean13("9556199", 2),
    })["id"]
    for code, name, product, recipe in (
        ("RCP-HMP-01", "Festive Goodies Hamper - standard box", hamper.id, HAMPER_RECIPE),
        ("RCP-KIT-01", "Kopitiam Breakfast Starter Kit", kit_id, KIT_RECIPE),
    ):
        api.post("admin", "/recipes", {
            "code": code, "name": name, "product_item_id": product, "output_qty": "1",
            "remark": "Assembled in the packing area from stock items",
            "lines": [{"item_id": sim.items[sku].id, "uom_id": sim.uoms[sim.items[sku].base], "qty": str(qty)}
                      for sku, qty in recipe],
        })

    with SessionLocal() as db:
        # Carton barcodes (GTIN-14) next to each item's unit barcode, so a scanner can read either
        for item in sim.items.values():
            if item.per_ctn:
                unit = db.execute(text("SELECT barcode FROM item WHERE id = :i"), {"i": item.id}).scalar()
                db.add(ItemBarcode(tenant_id=tenant_id, item_id=uuid.UUID(item.id), barcode=gtin14(unit), uom_id=uuid.UUID(sim.uoms["CTN"])))
        # A customer orders through the shopping cart on its own account
        customer = next(c for c in sim.customers if c.code == PORTAL_CUSTOMER)
        role = db.scalars(select(Role).where(Role.tenant_id == tenant_id, Role.code == "CUSTOMER")).first()
        user = db.scalars(select(User).where(User.tenant_id == tenant_id, User.username == "mutiara.orders")).first()
        if user is None:
            user = User(tenant_id=tenant_id, username="mutiara.orders", display_name="Pasar Mini Mutiara (ordering)",
                        email="orders@pasarminimutiara.example", password_hash=hash_password(password))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_id=role.id))
        user.partner_id = uuid.UUID(customer.id)
        api.user_ids["mutiara.orders"] = user.id
        sim.portal_user = "mutiara.orders"
        sim.reasons.update({
            f"RET:{r.code}": str(r.id)
            for r in db.scalars(select(ReasonCode).where(ReasonCode.tenant_id == tenant_id, ReasonCode.category == "RETURN"))
        })
        db.commit()
    print("Created features, QA hold area, label profiles, returnable assets, ERP connector, recipes, portal user")


def returnable_assets(sim: Sim, api: Api, rng, so: OpenSo, ship: dict) -> None:
    """Fresh milk goes out in crates, big drops on pallets, hotels get roll cages; empties come back on the next drop"""
    by_id = all_items(sim)
    crates = cartons = 0.0
    for line in ship["lines"]:
        item = by_id.get(line["item"]["id"].lower())
        if item is None:
            continue
        ctn = float(line["qty_actual"]) / item.order_factor
        cartons += ctn
        if item.zone == "CHL":
            crates += ctn
    wanted = {"CRT-MILK": math.ceil(crates), "PLT-STD": math.ceil(cartons / 45) if cartons >= 40 else 0,
              "CAGE-RL": 1 if so.customer.kind == "HOTEL" else 0}
    for code, qty in wanted.items():
        key = (so.customer.code, code)
        back = math.floor(sim.out_assets[key] * rng.uniform(0.7, 1.0))
        if back > 0:
            api.post(SUPERVISOR, "/returnable-assets/transactions", {
                "partner_id": so.customer.id, "asset_type_id": sim.assets[code], "txn_type": "RETURN", "qty": str(back),
                "remark": "Empties collected on delivery"})
            sim.out_assets[key] -= back
        if qty > 0:
            api.post(SUPERVISOR, "/returnable-assets/transactions", {
                "partner_id": so.customer.id, "asset_type_id": sim.assets[code], "txn_type": "ISSUE", "qty": str(qty),
                "ref_document_id": ship["id"]})
            sim.out_assets[key] += qty


def customer_returns(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE, tenant_id) -> None:
    recent = [s for s in sim.shipped if 0 < (day - s[0]).days <= 10]
    if not recent or rng.random() > 0.14 or not clock.at(day, 10.4):
        return
    _, so_id, customer, lines = rng.choice(recent)
    line = rng.choice(lines)
    item = all_items(sim).get(line["item"]["id"].lower())
    if item is None or item.sku.startswith("HMP"):
        return
    reason = rng.choice(["DAMAGED", "DAMAGED", "WRONG", "CUSTOMER", "EXPIRY" if item.zone == "CHL" else "QUALITY"])
    qty = min(float(line["qty_actual"]), rng.randint(1, max(1, item.order_factor // 2)))
    restock = reason in ("WRONG", "CUSTOMER")
    body = {
        "partner_id": customer.id, "ref_document_id": so_id, "reason_code_id": sim.reasons[f"RET:{reason}"],
        "remark": {"DAMAGED": "Damaged in transit, customer refused", "WRONG": "Wrong item delivered, picked against wrong bin",
                   "CUSTOMER": "Customer over-ordered, returned unopened", "EXPIRY": "Short dated on arrival",
                   "QUALITY": "Customer complaint: packaging defect"}[reason],
        "lines": [{"item_id": item.id, "uom_id": sim.uoms[item.base], "qty": q(qty), "batch_no": line["batch_no"],
                   "expiry_date": line["expiry_date"], "disposition": "RESTOCK" if restock else "SCRAP",
                   "location_id": home_bin(sim, tenant_id, item) if restock else None, "ref_line_id": line["ref_line_id"]}],
    }
    doc = api.post(SUPERVISOR, "/returns-in", body, ok=False)
    if doc is None:
        return
    if not restock:
        attach(api, SUPERVISOR, doc["id"], f"Return {doc['doc_no']}: {item.name} - {body['remark']}", rng)
    if clock.at(day, 10.6):
        api.post(SUPERVISOR, f"/returns-in/{doc['id']}/post")
        sim.stats["RETURN_IN"] += 1


def supplier_returns(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE, tenant_id) -> None:
    """Thursdays: stock dated within a week goes back to the supplier for credit"""
    if day.weekday() != 3 or not clock.at(day, 14.2):
        return
    rows = db_rows(
        "SELECT b.item_id, b.location_id, b.batch_no, b.expiry_date, b.qty_on_hand - b.qty_allocated FROM stock_balance b "
        "JOIN location l ON l.id = b.location_id WHERE b.tenant_id = :t AND l.location_type = 'BIN' AND b.expiry_date >= :d "
        "AND b.expiry_date < :e AND b.qty_on_hand - b.qty_allocated > 0",
        t=tenant_id, d=day, e=day + _dt.timedelta(days=7),
    )
    by_id, by_supplier = all_items(sim), defaultdict(list)
    for item_id, loc, batch, expiry, qty in rows:
        item = by_id.get(str(item_id).lower())
        if item and item.supplier and (item.shelf or 0) >= 20:
            by_supplier[item.supplier].append((item, loc, batch, expiry, qty))
    for key, lines in by_supplier.items():
        doc = api.post(SUPERVISOR, "/returns-out", {
            "partner_id": sim.suppliers[key].id, "reason_code_id": sim.reasons["RET:EXPIRY"],
            "remark": "Near-expiry stock returned for credit as agreed in the trading terms",
            "lines": [{"item_id": i.id, "uom_id": sim.uoms[i.base], "qty": q(qty), "batch_no": b,
                       "expiry_date": e.isoformat() if e else None, "location_id": str(loc)} for i, loc, b, e, qty in lines[:6]],
        }, ok=False)
        if doc and api.post(SUPERVISOR, f"/returns-out/{doc['id']}/post", ok=False) is not None:
            sim.stats["RETURN_OUT"] += 1


def consolidation_moves(sim: Sim, api: Api, clock: Clock, day: REAL_DATE, tenant_id) -> None:
    """Wednesdays: an item spread over two bins is brought together, freeing a bin"""
    if day.weekday() != 2 or not clock.at(day, 10.0):
        return
    rows = db_rows(
        "SELECT b.item_id, b.location_id, SUM(b.qty_on_hand), SUM(b.qty_allocated) FROM stock_balance b JOIN location l "
        "ON l.id = b.location_id WHERE b.tenant_id = :t AND l.location_type = 'BIN' AND l.is_pickable = 1 AND b.qty_on_hand > 0 "
        "GROUP BY b.item_id, b.location_id", t=tenant_id)
    spread = defaultdict(list)
    for item_id, loc, qty, allocated in rows:
        spread[str(item_id).lower()].append((float(qty), float(allocated), str(loc)))
    by_id, moved = all_items(sim), 0
    for item_id, bins in spread.items():
        if len(bins) < 2 or moved >= 3 or item_id not in by_id:
            continue
        bins.sort(reverse=True)
        (_, _, target), (_, allocated, source) = bins[0], bins[-1]
        if allocated > 0:
            continue
        item = by_id[item_id]
        lines = [{"item_id": item.id, "uom_id": sim.uoms[item.base], "qty": q(qty), "batch_no": b,
                  "expiry_date": e.isoformat() if e else None, "from_location_id": source, "to_location_id": target}
                 for loc, b, e, qty in bin_balances(tenant_id, item.id) if str(loc).lower() == source.lower()]
        if not lines or not clock.at(day, 10.0 + moved * 0.3):
            continue
        move = api.post(RECEIVER, "/moves", {"remark": "Consolidate into one bin", "lines": lines}, ok=False)
        if move and api.post(RECEIVER, f"/moves/{move['id']}/post", ok=False) is not None:
            moved += 1
            sim.stats["MOVE"] += 1


def cycle_count(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE, tenant_id, n: int) -> None:
    """Saturdays: the next dozen stocked bins (rotating through the warehouse) are counted. Most agree; a
    discrepancy is recounted before posting"""
    if day.weekday() != 5 or not clock.at(day, 11.0):
        return
    rows = db_rows(
        "SELECT location_id, SUM(qty_allocated) FROM stock_balance WHERE tenant_id = :t AND qty_on_hand > 0 GROUP BY location_id",
        t=tenant_id)
    stocked = {str(r[0]).lower(): float(r[1]) for r in rows}
    countable = [b for zone in ("AMB", "CHL", "FRZ") for b in sim.bins[zone] if stocked.get(b.lower(), 1) == 0]
    if not countable:
        return
    start = (n * 12) % len(countable)
    chosen = (countable[start:] + countable[:start])[:12]
    count = api.post(SUPERVISOR, "/cycle-counts", {"location_ids": chosen, "remark": f"Weekly cycle count, round {n + 1}"}, ok=False)
    if count is None:
        return
    hour, odd = 11.0, None
    for line in count["lines"]:
        hour += rng.uniform(0.03, 0.06)
        clock.at(day, hour)
        qty = float(line["qty_planned"])
        if odd is None and rng.random() < 0.35 and qty > 4:
            odd, qty = line, qty - rng.randint(1, 2)
        api.post(RECEIVER, f"/cycle-counts/{count['id']}/counts", {
            "location_id": line["to_location"]["id"], "item_id": line["item"]["id"], "qty": q(qty),
            "batch_no": line["batch_no"], "expiry_date": line["expiry_date"]}, idem=True)
    if odd is not None and clock.at(day, hour + 0.2):
        api.post(SUPERVISOR, f"/cycle-counts/{count['id']}/recount", {"line_ids": [odd["id"]]})
        clock.at(day, hour + 0.35)
        again = float(odd["qty_planned"]) - (rng.randint(1, 2) if rng.random() < 0.6 else 0)
        api.post("hafiz.rahman", f"/cycle-counts/{count['id']}/counts", {
            "location_id": odd["to_location"]["id"], "item_id": odd["item"]["id"], "qty": q(again),
            "batch_no": odd["batch_no"], "expiry_date": odd["expiry_date"]}, idem=True)
    if clock.at(day, hour + 0.5):
        api.post(SUPERVISOR, f"/cycle-counts/{count['id']}/post")
        sim.stats["COUNT"] += 1


def batch_recall(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE, tenant_id) -> None:
    """Crispy Valley recalls one batch of potato chips (seal defect): quarantine, return to the supplier, release"""
    item = sim.items["SNK-6003"]
    batches = [r for r in bin_balances(tenant_id, item.id) if r[1]]
    if not batches or not clock.at(day, 9.6):
        return
    batch = batches[0][1]
    recall = api.post("admin", "/recalls", {
        "item_id": item.id, "batch_no": batch, "quarantine_location_id": sim.qa_bins[0],
        "reason": f"Supplier notice CV-QA-2026-07: heat seal defect on batch {batch}, packs may be stale. Hold and return.",
    }, ok=False)
    if recall is None:
        return
    sim.recall_done = True
    clock.at(day, 9.9)
    for move in recall["moves"]:
        api.post(RECEIVER, f"/moves/{move['id']}/post", ok=False)
    held = db_rows("SELECT location_id, expiry_date, qty_on_hand FROM stock_balance WHERE tenant_id = :t AND item_id = :i "
                   "AND batch_no = :b AND location_id = :l AND qty_on_hand > 0", t=tenant_id, i=item.id, b=batch, l=sim.qa_bins[0])
    if held and clock.at(day, 14.0):
        loc, expiry, qty = held[0]
        out = api.post(SUPERVISOR, "/returns-out", {
            "partner_id": sim.suppliers["SNK"].id, "reason_code_id": sim.reasons["RET:QUALITY"],
            "ref_document_id": None, "remark": f"Recall {recall['document']['doc_no']}: batch {batch} collected by supplier",
            "lines": [{"item_id": item.id, "uom_id": sim.uoms[item.base], "qty": q(qty), "batch_no": batch,
                       "expiry_date": expiry.isoformat() if expiry else None, "location_id": str(loc)}],
        }, ok=False)
        if out:
            attach(api, SUPERVISOR, out["id"], f"Recalled batch {batch} wrapped and labelled for supplier pickup", rng)
            api.post(SUPERVISOR, f"/returns-out/{out['id']}/post", ok=False)
    if clock.at(day, 16.0):
        api.post("admin", f"/recalls/{recall['document']['id']}/release", ok=False)
    sim.stats["RECALL"] += 1


def hamper_repack(sim: Sim, api: Api, rng, clock: Clock, day: REAL_DATE, tenant_id, next_day: REAL_DATE) -> None:
    """Festive hampers are assembled from stock items, then sold to corporate customers"""
    if not clock.at(day, 9.5):
        return
    count = 40
    inputs = []
    for sku, per in HAMPER_RECIPE:
        item, need = sim.items[sku], per * count
        for loc, batch, expiry, avail in bin_balances(tenant_id, sim.items[sku].id):
            take = min(float(avail), need)
            inputs.append({"item_id": item.id, "uom_id": sim.uoms[item.base], "qty": q(take), "batch_no": batch,
                           "expiry_date": expiry.isoformat() if expiry else None, "location_id": str(loc)})
            need -= take
            if need <= 0:
                break
        if need > 0:
            return  # not enough components today
    target = free_bin(sim, tenant_id, "AMB")
    repack = api.post(SUPERVISOR, "/repacks", {
        "remark": f"Festive hamper assembly, recipe RCP-HMP-01 x {count}", "inputs": inputs,
        "outputs": [{"item_id": sim.hamper.id, "uom_id": sim.uoms["BOX"], "qty": str(count), "location_id": target}],
    }, ok=False)
    if repack is None:
        return
    clock.at(day, 12.0)
    api.post(SUPERVISOR, f"/repacks/{repack['id']}/post")
    sim.repack_done = True
    sim.stats["REPACK"] += 1
    for code, qty in (("C20005", 24), ("C20010", 12)):
        customer = next(c for c in sim.customers if c.code == code)
        clock.at(day, 12.3)
        so = api.post(OFFICE, "/sales-orders", {
            "partner_id": customer.id, "expected_date": next_day.isoformat(), "remark": "Corporate festive gifts for staff",
            "lines": [{"item_id": sim.hamper.id, "uom_id": sim.uoms["BOX"], "qty": str(qty)}]})
        api.post(OFFICE, f"/sales-orders/{so['id']}/confirm")
        sim.sos[so["id"]] = OpenSo(so["id"], customer, day)


class FakeErp:
    """Stands in for the ERP's webhook endpoint while the simulated worker delivers events"""

    def __init__(self, rng, fix_day: REAL_DATE, outage_day: REAL_DATE):
        self.rng, self.fix_day, self.outage_day = rng, fix_day, outage_day
        self.ref = 48211

    def __call__(self, target: dict, job_id):
        now = FakeDatetime.now()
        if now.date() == self.outage_day:
            return None, None, "URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>"
        payload = target["payload"]
        if target["event_type"] == "shipment.posted" and "C20024" in payload and now.date() < self.fix_day:
            return 422, '{"error": "customer_not_found", "detail": "Customer C20024 is not mapped in ERP"}', "HTTP 422"
        if self.rng.random() < 0.02:
            return 503, '{"error": "service_unavailable", "detail": "ERP is busy, retry later"}', "HTTP 503"
        self.ref += 1
        return 200, f'{{"status": "accepted", "erp_ref": "ERP-{self.ref}"}}', None


def run_worker(clock: Clock, day: REAL_DATE, fake_erp: FakeErp) -> None:
    """What the background worker would have done that day: turn events into jobs and deliver them, with retries"""
    from app.core.db import SessionLocal
    from app.services import integration_service as integration

    integration._post = fake_erp
    for step in range(8):
        if not clock.at(day, 18.0 + step * 0.5):
            return
        with SessionLocal() as db:
            while integration.dispatch_events(db):
                pass
            for job_id in integration.claim_jobs(db, batch=500):
                integration.deliver(db, job_id)


def finishing_touches(sim: Sim, api: Api, clock: Clock, tenant_id, today: REAL_DATE, days) -> None:
    """Saved carts, an assistant conversation history and the worker heartbeat"""
    import json

    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models.assistant import AssistantConversation, AssistantMessage
    from app.services import integration_service as integration

    portal = next(c for c in sim.customers if c.code == PORTAL_CUSTOMER)
    cart = {"partner": {"id": portal.id, "code": portal.code, "name": portal.name},
            "lines": [{"item_id": sim.items[s].id, "uom_id": sim.uoms["CTN"], "qty": n}
                      for s, n in (("BEV-1001", 10), ("SNK-6005", 6), ("DRY-2007", 4))]}
    api.call(sim.portal_user, "PUT", "/me/preferences/cart", {"value": cart}, ok=False)
    api.call(OFFICE, "PUT", "/me/preferences/cart", {"value": {"partner": None, "lines": []}}, ok=False)

    low = db_rows(
        "SELECT i.sku_code, i.name, SUM(b.qty_on_hand - b.qty_allocated), i.min_stock_qty FROM item i LEFT JOIN stock_balance b "
        "ON b.item_id = i.id WHERE i.tenant_id = :t AND i.min_stock_qty IS NOT NULL GROUP BY i.sku_code, i.name, i.min_stock_qty "
        "HAVING COALESCE(SUM(b.qty_on_hand - b.qty_allocated), 0) < i.min_stock_qty ORDER BY i.sku_code", t=tenant_id)
    yesterday = days[-2]
    shipped = db_rows("SELECT COUNT(*) FROM document_header WHERE tenant_id = :t AND doc_type = 'SHIP' AND status = 'POSTED' "
                      "AND CAST(posted_at AS date) = :d", t=tenant_id, d=yesterday)[0][0]
    low_text = "\n".join(f"- {sku} {name}: {float(a or 0):,.0f} available, minimum {float(m):,.0f}" for sku, name, a, m in low[:8])
    talks = [
        (days[-6], 17.2, "Which items are below their minimum stock right now?",
         (f"{len(low)} items are below their minimum stock:\n{low_text}\n\nMost of them are already on open purchase orders; "
          "check Purchasing > Purchase orders for the expected dates.") if low else "No item is below its minimum stock right now."),
        (today, 8.1, f"How many delivery orders did we ship on {yesterday:%d %b}?",
         f"{shipped} delivery orders were posted on {yesterday:%A %d %B %Y}."),
    ]
    with SessionLocal() as db:
        for day, hour, question, answer in talks:
            if not clock.at(day, hour):
                continue
            when = FakeDatetime.now(_dt.UTC).replace(tzinfo=None)
            convo = AssistantConversation(tenant_id=tenant_id, user_id=api.user_ids[SUPERVISOR], title=question[:200],
                                          created_by=api.user_ids[SUPERVISOR], updated_by=api.user_ids[SUPERVISOR])
            db.add(convo)
            db.flush()
            db.add(AssistantMessage(tenant_id=tenant_id, conversation_id=convo.id, seq=1, role="user",
                                    content=json.dumps([{"type": "text", "text": question}]), created_at=when))
            db.add(AssistantMessage(tenant_id=tenant_id, conversation_id=convo.id, seq=2, role="assistant",
                                    content=json.dumps([{"type": "text", "text": answer}]),
                                    created_at=when + _dt.timedelta(seconds=6), model=settings.ai_model, stop_reason="end_turn",
                                    input_tokens=5800 + len(answer), output_tokens=len(answer) // 3, cache_read_tokens=4200))
        db.commit()
    clock.reset()
    with SessionLocal() as db:
        integration.heartbeat(db, "demo data: deliveries simulated up to now")


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace all data of the tenant with a realistic demo dataset")
    parser.add_argument("--confirm", action="store_true", help="confirm that all existing data of the tenant may be deleted")
    parser.add_argument("--days", type=int, default=60, help="days of operations to simulate, ending today")
    parser.add_argument("--seed", type=int, default=2026, help="random seed")
    args = parser.parse_args()

    from app.core.config import settings

    if settings.app_env == "production":
        raise SystemExit("Refusing to run against a production environment")
    if not args.confirm:
        raise SystemExit("This deletes every item, location, partner and document of the tenant. Add --confirm to proceed")

    install_clock()
    import logging
    import warnings

    for name in ("httpx", "httpx2", "wms.request", "wms"):
        logging.getLogger(name).setLevel(logging.WARNING)
    warnings.filterwarnings("ignore", module="jwt")
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.tenant import Tenant

    tenant_code = os.environ.get("SEED_TENANT_CODE", "DEFAULT")
    with SessionLocal() as db:
        tenant = db.scalars(select(Tenant).where(Tenant.code == tenant_code)).first()
        if tenant is None:
            raise SystemExit(f"Tenant {tenant_code} not found: run python -m scripts.seed first")
        tenant_id, tz = tenant.id, ZoneInfo(settings.business_timezone)

    rng = random.Random(args.seed)
    clock = Clock(tz)
    sim = Sim()
    api = Api(tenant_id)
    started = time.time()

    today = clock.real_now().date()
    start = today - _dt.timedelta(days=args.days)
    days = working_days(start, today)
    go_live, sales_start = days[0], days[2]

    wipe(tenant_id)
    ensure_uoms_and_users(sim, api, tenant_id, os.environ.get("DEMO_PASSWORD", "Demo@2026"))
    clock.at(go_live - _dt.timedelta(days=4), 10.0)
    create_locations(sim, api)
    create_partners(sim, api)
    create_items(sim, api)
    create_extra_master(sim, api, tenant_id, os.environ.get("DEMO_PASSWORD", "Demo@2026"))
    sales_days = [d for d in days if d >= sales_start]
    plans = plan_orders(sim, rng, sales_days)
    set_min_stock(sim, api)

    # Prices: cooking oil went up 6% halfway through (CPO price), everything else drifts a little
    price_steps = {sku: Decimal(str(round(rng.uniform(0.98, 1.03), 3))) for sku in sim.items}
    midpoint = days[len(days) // 2]

    def price_factor(item: Item, day: REAL_DATE) -> Decimal:
        if item.key == "oil" and item.base == "BTL" and day >= midpoint:
            return Decimal("1.06")
        return price_steps[item.sku] if day >= midpoint else Decimal(1)

    # Go-live: opening orders to every supplier for about three weeks of stock (a week for fresh goods)
    clock.at(go_live, 8.5)
    for supplier in sim.suppliers.values():
        lines = []
        for item in sim.items.values():
            if item.supplier == supplier.key and item.daily_base > 0:
                cover = 6 if (item.shelf or 999) < 30 else 20
                lines.append((item, math.ceil(item.daily_base * cover / item.order_factor)))
        if not lines:
            continue
        create_po(sim, api, rng, supplier, go_live, lines, confirm=True, price_factor=price_factor)
        po = list(sim.pos.values())[-1]
        po.due = go_live if supplier.lead <= 2 else days[1]
    print(f"Master data ready ({time.time() - started:.0f}s); simulating {len(days)} working days {go_live} .. {today}")

    fake_erp = FakeErp(rng, days[int(len(days) * ERP_FIX_DAY_FRACTION)], days[int(len(days) * 0.8)])
    repack_day, recall_day = days[int(len(days) * 0.5)], days[int(len(days) * 0.65)]
    by_day = defaultdict(list)
    for plan in plans:
        by_day[plan.day].append(plan)
    for n, day in enumerate(days):
        next_day = days[n + 1] if n + 1 < len(days) else day + _dt.timedelta(days=1)
        dispatch(sim, api, rng, clock, day)
        write_offs(sim, api, rng, clock, day, tenant_id)
        order_intake(sim, api, clock, by_day.get(day, []), day, next_day)
        receiving(sim, api, rng, clock, day, tenant_id)
        safely(customer_returns, sim, api, rng, clock, day, tenant_id)
        safely(consolidation_moves, sim, api, clock, day, tenant_id)
        safely(cycle_count, sim, api, rng, clock, day, tenant_id, n // 6)
        if day >= repack_day and not sim.repack_done:
            safely(hamper_repack, sim, api, rng, clock, day, tenant_id, next_day)
        if day >= recall_day and not sim.recall_done:
            safely(batch_recall, sim, api, rng, clock, day, tenant_id)
        purchasing(sim, api, rng, clock, day, tenant_id, price_factor, today)
        picking(sim, api, rng, clock, day, days)
        safely(supplier_returns, sim, api, rng, clock, day, tenant_id)
        payments(sim, api, clock, day, today)
        safely(run_worker, clock, day, fake_erp)
        print(f"  {day:%a %Y-%m-%d}  " + "  ".join(f"{k} {v}" for k, v in sorted(sim.stats.items()))
              + f"  ({time.time() - started:.0f}s)", flush=True)

    safely(finishing_touches, sim, api, clock, tenant_id, today, days)
    clock.reset()
    if FAILURES:
        print(f"{len(FAILURES)} optional steps failed and were skipped:")
        for failure in FAILURES[:20]:
            print("  " + failure)
    print(f"Done in {time.time() - started:.0f}s. Demo staff: " + ", ".join(u for u, _, _ in STAFF)
          + " (password Demo@2026 unless DEMO_PASSWORD was set)")


if __name__ == "__main__":
    main()
