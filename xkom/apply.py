"""
Część "GO": otwiera x-kom w przeglądarce (profil zapamiętany w state/browser),
dodaje produkt (jeśli podano) i aplikuje kod rabatowy w koszyku.
Przeglądarka zostaje otwarta, żebyś mógł dokończyć zamówienie ręcznie.
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from .common import ROOT, STATE, LOGS, log, load_config

CART_URL = "https://www.x-kom.pl/koszyk.html"

PROMO_INPUT_SELECTORS = [
    'input[placeholder*="kod" i]',
    'input[name*="promo" i]',
    'input[name*="coupon" i]',
    'input[id*="promo" i]',
    'input[id*="coupon" i]',
]
APPLY_BTN_SELECTORS = [
    'button:has-text("Dodaj")',
    'button:has-text("Użyj")',
    'button:has-text("Zastosuj")',
    'button:has-text("Zastosuj kod")',
    'button[type="submit"]',
]


def _shot(page, name):
    p = LOGS / f"apply_{int(time.time())}_{name}.png"
    try:
        page.screenshot(path=str(p), full_page=True)
        log(f"zrzut: {p}")
    except Exception:
        pass
    return p


def _find_promo_input(page):
    for sel in PROMO_INPUT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=2000):
                return loc
        except Exception:
            continue
    return None


def _find_apply_btn(page):
    for sel in APPLY_BTN_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=1500):
                return loc
        except Exception:
            continue
    return None


def apply_code(code, product_url=None, product_search=None, headless=False):
    """
    Aplikuje kod w koszyku x-kom.
    product_url — dokładny URL produktu (bot sam go doda do koszyka),
    product_search — fraza szukajki, jeśli nie znasz URL-a.
    Zwraca dict z wynikiem.
    """
    cfg = load_config()
    xk = cfg.get("xkom") or {}
    cart_url = xk.get("cart_url", CART_URL)
    keep_open = (xk.get("keep_open_after_apply_sec") or 600)
    profile_dir = str(ROOT / (xk.get("browser_dir") or "state/browser"))

    result = {"code": code, "ok": False, "details": "", "screenshot": None}

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            profile_dir,
            headless=headless,
            viewport={"width": 1440, "height": 900},
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(30_000)

        # 1) produkt do koszyka (jeśli podano)
        if product_url:
            log(f"dodaję produkt do koszyka: {product_url}")
            try:
                page.goto(product_url, wait_until="domcontentloaded")
                btn = page.locator('button:has-text("Do koszyka"), button:has-text("Dodaj do koszyka")').first
                if btn.is_visible(timeout=8000):
                    btn.click()
                    page.wait_for_timeout(4000)
                    result["added_to_cart"] = True
                else:
                    result["details"] += "Nie znalazłem przycisku 'Do koszyka' na stronie produktu. "
            except Exception as e:
                result["details"] += f"Błąd dodawania produktu: {e} "

        if product_search and not product_url:
            log(f"szukam produktu: {product_search}")
            try:
                page.goto(f"https://www.x-kom.pl/szukaj?q={product_search}", wait_until="domcontentloaded")
                first = page.locator('[data-test*="product"], .productCard, .product-card, a[href*="/p/"]').first
                if first.is_visible(timeout=8000):
                    href = first.get_attribute("href")
                    if href and href.startswith("http"):
                        page.goto(href, wait_until="domcontentloaded")
                        btn = page.locator('button:has-text("Do koszyka")').first
                        if btn.is_visible(timeout=6000):
                            btn.click()
                            page.wait_for_timeout(4000)
                            result["added_to_cart"] = True
            except Exception as e:
                result["details"] += f"Błąd szukania produktu: {e} "

        # 2) koszyk + kod
        log(f"otwieram koszyk: {cart_url}")
        page.goto(cart_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        inp = _find_promo_input(page)
        if inp is None:
            result["details"] += "Nie znalazłem pola na kod rabatowy w koszyku (może pusty koszyk lub zmiana w UI). "
            result["screenshot"] = str(_shot(page, "no_field"))
            ctx.close()
            return result

        for attempt in range(1, 4):
            log(f"aplikuję kod (próba {attempt}/3)")
            inp.click()
            inp.fill(code)
            inp.press("Enter")
            btn = _find_apply_btn(page)
            if btn:
                try:
                    btn.click()
                except Exception:
                    pass
            page.wait_for_timeout(3500)

            # sprawdzenie wyniku: komunikat o błędzie?
            err = page.locator('text=/nie jest prawidłowy|nieprawidłowy|błędny kod|nie istnieje|przestał obowiązywać|nie może być/i')
            if err.count() > 0:
                msg = err.first.inner_text()
                result["details"] += f"Kod odrzucony przez sklep: '{msg}' "
                result["screenshot"] = str(_shot(page, f"rejected_{attempt}"))
                break

            # sukces: rabat naliczony / cena 1 zł
            ok = page.locator(r'text=/rabat|kod.*zastosowano|1,00 ?zł|1\.00 ?zł/i')
            if ok.count() > 0:
                result["ok"] = True
                result["details"] = (result["details"] + "Kod ZAAKTYWOWANY ✓ — dokończ zamówienie w przeglądarce!")
                result["screenshot"] = str(_shot(page, "applied"))
                log("KOD ZAAKTYWOWANY ✓")
                break
            log(f"próba {attempt}: brak jasnego wyniku, sprawdzam dalej")

        if not result["ok"] and not result["details"]:
            result["details"] = "Kod wpisany, ale nie potwierdzam sukcesu — sprawdź koszyk ręcznie."
        if result["screenshot"] is None:
            result["screenshot"] = str(_shot(page, "final"))

        log(f"pozostawiam przeglądarkę otwartą na {keep_open}s...")
        try:
            page.wait_for_timeout(int(keep_open * 1000))
        except Exception:
            pass
        ctx.close()

    return result
