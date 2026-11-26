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
    p1 = r"(?:CHF|EUR|€|Fr\.?)\s*(\d{1,4}['’.,]?\d{1,3}(?:[.,]\d{2}|[.,]-)?)"
    p2 = r"(\d{1,4}['’.,]?\d{1,3}(?:[.,]\d{2}|[.,]-)?)\s*(?:CHF|EUR|€|Fr\.?)"
    matches = re.findall(f"(?:{p1}|{p2})", text, flags=re.I)

    prices = []
    for m1, m2 in matches:
        raw_num = m1 or m2
        clean = raw_num.replace("'", "").replace("’", "").replace(".-", ".00").replace(",-", ".00")
        if "," in clean and "." in clean:
            if clean.rfind(",") > clean.rfind("."):
                clean = clean.replace(".", "").replace(",", ".")
            else:
                clean = clean.replace(",", "")
        elif "," in clean:
            clean = clean.replace(",", ".")
        elif clean.count(".") == 1 and len(clean.split(".")[1]) == 3:
            clean = clean.replace(".", "")
        try:
            val = float(clean)
            if min_limit <= val <= 1000:
                prices.append(val)
        except ValueError:
            continue
    return min(prices) if prices else None

def is_valid_homee(text):
    t = text.lower()
    if "homee" not in t:
        return False
    if not any(brand in t for brand in ["hörmann", "hoermann", "hormann"]):
        return False
    if any(bad in t for bad in BLACKLIST):
        return False
    return True

async def scan_target(semaphore, context, target, seen_cache):
    async with semaphore:
        page = await context.new_page()
        currency = target["currency"]
        default_min = MIN_PREIS_CHF if currency == "CHF" else MIN_PREIS_EUR
        min_limit = target.get("min_price", default_min)
        max_limit = MAX_PREIS_CHF if currency == "CHF" else MAX_PREIS_EUR
        hits = 0

        try:
            await page.goto(target["url"], wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)

            cards = await page.locator("a, article, li, div").filter(
                has_text=re.compile(r"homee", re.I)
            ).all()

            for card in cards[:65]:
                try:
                    raw_text = await card.inner_text(timeout=350)
                    if len(raw_text) > 400 or len(raw_text) < 15:
                        continue
                    if not is_valid_homee(raw_text):
                        continue

                    price = parse_price(raw_text, min_limit)
                    if price and price <= max_limit:
                        lines = [l.strip() for l in raw_text.splitlines() if "homee" in l.lower()]
                        title = lines[0][:90] if lines else "Hörmann homee Brain"

                        href = await card.get_attribute("href")
                        if not href:
                            sub_link = card.locator("a").first
                            if await sub_link.count() > 0:
                                href = await sub_link.get_attribute("href")

                        full_url = target["url"]
                        if href:
                            if href.startswith("http"):
                                full_url = href
                            elif href.startswith("/"):
                                base = "/".join(target["url"].split("/")[:3])
                                full_url = base + href

                        deal_hash = hashlib.md5(f"{target['name']}_{int(price)}_{title[:35]}".encode()).hexdigest()
                        if deal_hash not in seen_cache:
                            seen_cache.add(deal_hash)
                            send_push(target["name"], title, price, currency, full_url)
                            hits += 1
                except Exception:
                    continue

            print(f"[OK] {target['name']}: {hits} neue Treffer ({min_limit}-{max_limit} {currency})")

        except Exception as e:
            print(f"[ÜBERSPRUNGEN] {target['name']}: {str(e).splitlines()[0]}")
        finally:
            await page.close()

async def main():
    seen_cache = load_cache()
    semaphore = asyncio.Semaphore(PARALLELE_TABS)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="de-CH",
            viewport={"width": 1366, "height": 900}
        )

        await context.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda route: route.abort())

        tasks = [scan_target(semaphore, context, target, seen_cache) for target in TARGETS]
        await asyncio.gather(*tasks)

        await browser.close()
    save_cache(seen_cache)

if __name__ == "__main__":
    asyncio.run(main())
