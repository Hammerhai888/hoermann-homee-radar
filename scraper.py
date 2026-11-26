import asyncio
import json
import os
import re
import hashlib
import requests
from playwright.async_api import async_playwright

# ==========================================
# 1. DEIN PUSH-KANAL FÜR HÖRMANN HOMEE (NTFY.SH)
# ==========================================
NTFY_TOPIC = "tobi_hoermann_homee_9941"

# ==========================================
# 2. PREIS-LIMITS (MAX: 200 EUR / 183 CHF)
# ==========================================
MIN_PREIS_CHF = 50.00    # Standard-Mindestpreis für Shops
MAX_PREIS_CHF = 183.00   # Entspricht 200 EUR beim aktuellen Kurs

MIN_PREIS_EUR = 54.50    # Standard-Mindestpreis für EU-Shops
MAX_PREIS_EUR = 200.00   # Maximales Budget EUR

CACHE_FILE = "seen_deals.json"
PARALLELE_TABS = 4

# ==========================================
# 3. AUSSCHLUSS-FILTER (INKL. BLAUER ZUSATZ-CUBE)
# ==========================================
BLACKLIST = [
    "netzteil", "kabel", "wandhalterung", "halterung", "ovp", "verpackung",
    "leerkarton", "defekt", "bastler", "handsender", "hse", "hsm", "hs5",
    "z-wave", "zwave", "zigbee", "enocean", "warema", "centronic",
    "bisecur-cube", "bisecur cube", "erweiterung", "zusatzwürfel",
    "abgelaufen", "beendet", "ausverkauft", "expired"
]

# ==========================================
# 4. AUKTIONEN AB 1 CHF/EUR, KLEINANZEIGEN, EU-AMAZONS & FACHHÄNDLER
# ==========================================
TARGETS = [
    # --- AUKTIONEN & KLEINANZEIGEN (AB 1 CHF / 1 EUR FREIGESCHALTET!) ---
    {"name": "Tutti.ch (Hörmann)", "currency": "CHF", "min_price": 1.00, "url": "https://www.tutti.ch/de/q/H%C3%B6rmann+homee"},
    {"name": "Tutti.ch (Hoermann)", "currency": "CHF", "min_price": 1.00, "url": "https://www.tutti.ch/de/q/Hoermann+homee"},
    {"name": "Ricardo.ch (Auktion & Sofort)", "currency": "CHF", "min_price": 1.00, "url": "https://www.ricardo.ch/de/s/H%C3%B6rmann%20homee/"},
    {"name": "Ricardo.ch (Hoermann)", "currency": "CHF", "min_price": 1.00, "url": "https://www.ricardo.ch/de/s/Hoermann%20homee/"},
    {"name": "Kleinanzeigen.de", "currency": "EUR", "min_price": 1.00, "url": "https://www.kleinanzeigen.de/s-h%C3%B6rmann-homee/k0"},
    {"name": "eBay.de (Auktion & Sofort)", "currency": "EUR", "min_price": 1.00, "url": "https://www.ebay.de/sch/i.html?_nkw=H%C3%B6rmann+homee"},
    {"name": "eBay.ch (Auktion & Sofort)", "currency": "CHF", "min_price": 1.00, "url": "https://www.ebay.ch/sch/i.html?_nkw=H%C3%B6rmann+homee"},
    {"name": "Willhaben.at", "currency": "EUR", "min_price": 1.00, "url": "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz?keyword=H%C3%B6rmann+homee"},

    # --- ALLE AMAZON-STORES IN DER UMGEBUNG (NEU & WAREHOUSE / RETOURENKAUF) ---
    {"name": "Amazon.de (Neu & Warehouse)", "currency": "EUR", "url": "https://www.amazon.de/s?k=H%C3%B6rmann+homee"},
    {"name": "Amazon.fr (Neu & Seconde Main)", "currency": "EUR", "url": "https://www.amazon.fr/s?k=Hormann+homee"},
    {"name": "Amazon.it (Neu & Seconda Mano)", "currency": "EUR", "url": "https://www.amazon.it/s?k=Hormann+homee"},
    {"name": "Amazon.es (Neu & Segunda Mano)", "currency": "EUR", "url": "https://www.amazon.es/s?k=Hormann+homee"},
    {"name": "Amazon.nl (Neu & Tweedekans)", "currency": "EUR", "url": "https://www.amazon.nl/s?k=Hormann+homee"},
    {"name": "Amazon.com.be (Belgien)", "currency": "EUR", "url": "https://www.amazon.com.be/s?k=Hormann+homee"},

    # --- PREISSUCHMASCHINEN IM DACH-RAUM ---
    {"name": "Toppreise.ch", "currency": "CHF", "url": "https://www.toppreise.ch/produktsuche?q=h%C3%B6rmann%20homee"},
    {"name": "Geizhals.de", "currency": "EUR", "url": "https://geizhals.de/?fs=H%C3%B6rmann+homee&hloc=de"},
    {"name": "Geizhals.at", "currency": "EUR", "url": "https://geizhals.at/?fs=H%C3%B6rmann+homee&hloc=at"},
    {"name": "idealo.de", "currency": "EUR", "url": "https://www.idealo.de/preisvergleich/MainSearchProductCategory.html?q=H%C3%B6rmann+homee"},
    {"name": "mydealz.de", "currency": "EUR", "url": "https://www.mydealz.de/search?q=H%C3%B6rmann+homee&hide_expired=true"},

    # --- SPEZIALISIERTE TOR-, ANTRIEBS- & SMART-HOME-HÄNDLER (CH & DE) ---
    {"name": "Scheurich24.ch (Tor-Fachhandel)", "currency": "CHF", "url": "https://www.scheurich24.ch/search?sSearch=H%C3%B6rmann+homee"},
    {"name": "Scheurich24.de (Tor-Fachhandel)", "currency": "EUR", "url": "https://www.scheurich24.de/search?sSearch=H%C3%B6rmann+homee"},
    {"name": "Tor7.de (Tor-Spezialist)", "currency": "EUR", "url": "https://www.tor7.de/search?sSearch=H%C3%B6rmann+homee"},
    {"name": "TorDoc.de (Tor-Fachhandel)", "currency": "EUR", "url": "https://www.tordoc.de/search?sSearch=H%C3%B6rmann+homee"},
    {"name": "Automatiktore24.de", "currency": "EUR", "url": "https://www.automatiktore24.de/search?sSearch=H%C3%B6rmann+homee"},
    {"name": "Handsender-Express.de", "currency": "EUR", "url": "https://www.handsender-express.de/search?sSearch=homee"},
    {"name": "Handsender.ch", "currency": "CHF", "url": "https://www.handsender.ch/search?sSearch=homee"},
    {"name": "Meissner-Torantriebe.de", "currency": "EUR", "url": "https://www.meissner-torantriebe.de/search?sSearch=H%C3%B6rmann+homee"},
    {"name": "ELV.com (Smart Home)", "currency": "EUR", "url": "https://de.elv.com/search?sSearch=H%C3%B6rmann+homee"},
    {"name": "Tink.de (Smart Home)", "currency": "EUR", "url": "https://www.tink.de/catalogsearch/result/?q=H%C3%B6rmann+homee"},
    {"name": "Reichelt.de (Elektronik)", "currency": "EUR", "url": "https://www.reichelt.de/index.html?ACTION=446&q=H%C3%B6rmann%20homee"},
    {"name": "Voelkner.de", "currency": "EUR", "url": "https://www.voelkner.de/search/search.html?keywords=H%C3%B6rmann%20homee"},
    {"name": "Galaxus.ch", "currency": "CHF", "url": "https://www.galaxus.ch/de/search?q=H%C3%B6rmann+homee"},
    {"name": "Digitec.ch", "currency": "CHF", "url": "https://www.digitec.ch/de/search?q=H%C3%B6rmann+homee"},
    {"name": "Brack.ch", "currency": "CHF", "url": "https://www.brack.ch/search?query=H%C3%B6rmann+homee"},
]

# ==========================================
# 5. PROGRAMM-LOGIK
# ==========================================
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_cache(cache_set):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(cache_set), f, indent=2)

def send_push(shop, title, price, currency, url):
    msg = f"{title}\nPreis: {price:.2f} {currency} ({shop})"
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=msg.encode("utf-8"),
            headers={
                "Title": f"Hörmann homee: {price:.2f} {currency} ({shop})".encode("utf-8"),
                "Click": url,
                "Tags": "house,rotating_light"
            },
            timeout=10
        )
        print(f"[PUSH] {msg}")
    except Exception as e:
        print(f"[PUSH FEHLER] {e}")

def parse_price(text, min_limit):
    pattern = r"(?:(?:CHF|EUR|€|Fr\.?)\s*(\d{1,4}['’.,]?\d{1,3}(?:[.,]\d{2}|[.,]-)?)|(\d{1,4}['’.,]?\d{1
