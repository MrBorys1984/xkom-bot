"""
Silnik zakupów x-kom: produkt -> koszyk -> kod -> kasa -> zamówienie.

Bezpieczeństwo:
- używa profilu przeglądarki state/browser (sesja, adresy i metody płatności
  zapisane w Twoim koncie x-kom — silnik wybiera to, co x-kom pokaże
  jako domyślne/z ostatniego zamówienia, NIGDY nie wpisuje danych karty)
- przed finalnym kliknięciem "Zamawiam i płacę" domyślnie STANIE i poprosi
  o potwierdzenie ENTER-em (chyba że --pay)
- na każdym kroku zrzut ekranu do state/logs/ (debug + dowód)
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from .common import ROOT, STATE, LOGS, log
from .apply import PROMO_INPUT_SELECTORS, APPLY_BTN_SELECTORS, _shot

CART_URL = "https://www.x-kom.pl/koszyk.html"

# przyciski "do kasy"
TO_CASH_SELECTORS = [
    'button:has-text("Do kasy")',
    'a:has-text("Do kasy")',
    'button:has-text("Przejdź do kasy")',
    'button:has-text("Kasa")',
    '[data-test*="checkout"]',
]
# finalny przycisk złożenia zamówienia
PLACE_ORDER_SELECTORS = [
    'button:has-text("Zamawiam i płacę")',
    'button:has-text("Złóż zamówienie")',
    'button:has-text("Zamawiam")',
    'button:has-text("Przejdź do płatności")',
]
# pola logowania (do wykrycia, że trzeba się zalogować)
LOGIN_HINTS = [
    'input[type="password"]',
    'a[href*="logowanie"]',
    'text=/zaloguj się|logowanie/i',
]


def _visible(page, sel, timeout=2500):
    try:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible(timeout=timeout):
            return loc
    except Exception:
        pass
    return None


def _click_first(page, selectors, what, screenshot_name=None):
    for sel in selectors:
        loc = _visible(page, sel)
        if loc:
            log(f"klikam [{what}]: {sel}")
            loc.click()
            if screenshot_name:
                _shot(page, screenshot_name)
            return True
    log(f"NIE ZNALAZŁEM elementu [{what}]")
    return False


def _page_text(page):
    try:
        return page.locator("body").inner_text(timeout=5000)[:20000]
    except Exception:
        return ""


def _wait_manual(page, hint, what, max_min=10):
    """Zostawia sterowanie u użytkownika (logowanie, captcha, ręczny wybór)."""
    _shot(page, "manual_wait")
    log(f"▶ MANUALNE: {hint}")
    print(f"\n  >>> {what}: {hint}", flush=True)
    t0 = time.time()
    while time.time() - t0 < max_min * 60:
        time.sleep(5)
    return


def run_checkout(product_url, code=None, auto_pay=False, headless=False,
                 expect_price_low=False):
    """
    product_url: URL produktu
    code:        kod rabatowy (opcjonalnie)
    auto_pay:    True = kliknij "Zamawiam i płacę" bez potwierdzenia ENTER
    expect_price_low: True = ostrzegaj, jeśli cena po rabacie nie jest niska (< 10 zł)
    """
    result = {"ok": False, "steps": [], "screenshot": None, "summary": ""}

    def step(name, ok=True, note=""):
        result["steps"].append({"step": name, "ok": ok, "note": note})
        log(f"[checkout] {name} {'✓' if ok else '✗'} {note}")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(ROOT / "state" / "browser"),
            headless=headless,
            viewport={"width": 1440, "height": 950},
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(30_000)

        try:
            # ---------- 1) produkt ----------
            step("otwieram produkt")
            page.goto(product_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            title = page.title()
            step("produkt", True, title[:80])

            # ---------- 2) do koszyka (jeśli jeszcze nie ma) ----------
            add = _visible(page, 'button:has-text("Do koszyka"), button:has-text("Dodaj do koszyka")')
            if add:
                add.click()
                page.wait_for_timeout(4000)
                step("dodałem do koszyka", True)
            else:
                step("produkt w koszyku", True, "brak przycisku (może już w koszyku)")

            # ---------- 3) koszyk + kod ----------
            page.goto(CART_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            if code:
                from .apply import _find_promo_input, _find_apply_btn
                inp = _find_promo_input(page)
                if inp:
                    for attempt in range(1, 4):
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
                        body = _page_text(page)
                        if "nie jest prawidłowy" in body or "błędny kod" in body.lower():
                            step(f"kod (próba {attempt})", False, "kod odrzucony")
                            result["screenshot"] = str(_shot(page, "code_rejected"))
                            break
                        if "1,00" in body or "zastosowano" in body.lower() or "rabat" in body.lower():
                            step(f"kod (próba {attempt})", True, "kod aktywny")
                            result["screenshot"] = str(_shot(page, "code_ok"))
                            break
                    else:
                        step("kod", True, "wpisany (brak jasnego potwierdzenia)")
                else:
                    step("kod", False, "nie znaleziono pola na kod")

            # sprawdź cenę przed kasą
            body = _page_text(page)
            for price_line in ("Do zapłaty", "Razem", "Suma"):
                idx = body.find(price_line)
                if idx >= 0:
                    result["summary"] += body[idx:idx + 80].replace("\n", " ") + " | "
            if expect_price_low and not any(p in body for p in ("1,00 zł", "1.00 zł", "0,01 zł")):
                log("OSTRZEŻENIE: nie widzę ceny ~1 zł w koszyku — sprawdź przed kasą!")

            # ---------- 4) kasa ----------
            if not _click_first(page, TO_CASH_SELECTORS, "do kasy", "to_cash"):
                _wait_manual(page, "Kliknij ręcznie 'Do kasy' w otwartej przeglądarce",
                             "przejście do kasy", max_min=5)
            page.wait_for_timeout(4000)

            # ---------- 5) logowanie (jeśli potrzebne) ----------
            login = _visible(page, 'input[type="password"]', timeout=5000)
            if login or any(_visible(page, s, timeout=1500) for s in LOGIN_HINTS[1:]):
                _wait_manual(page, "Zaloguj się do x-kom ręcznie w otwartej przeglądarce",
                             "logowanie x-kom", max_min=15)
                page.wait_for_timeout(3000)

            # ---------- 6) adres / dostawa / płatność ----------
            # x-kom podpowiada dane z ostatniego zamówienia (radiobuttony) —
            # klikamy TYLKO to, co nie jest zaznaczone, żeby nie psuć domyślnego.
            # adres
            addr_radio = page.locator('input[type="radio"][name*="address" i], '
                                      'input[type="radio"][name*="adres" i]')
            if addr_radio.count():
                first = addr_radio.nth(0)
                if not first.is_checked():
                    first.check()
                    log("wybrany pierwszy (zapisany) adres")
                else:
                    log("adres domyślny już zaznaczony")
            # dostawa
            ship = _visible(page, 'input[type="radio"][name*="delivery" i], '
                                  'input[type="radio"][name*="dostaw" i], '
                                  'label:has-text("Kurier")')
            if ship:
                try:
                    if ship.get_attribute("type") == "radio" and not ship.is_checked():
                        ship.check()
                except Exception:
                    pass
            # płatność: zostawiamy domyślną (z ostatniego zamówienia)
            pay_radio = page.locator('input[type="radio"][name*="pay" i], '
                                     'input[type="radio"][name*="platnosc" i]')
            checked = [i for i in range(pay_radio.count()) if pay_radio.nth(i).is_checked()]
            if checked:
                log(f"płatność: używam domyślnej (zaznaczonej) opcji")
            else:
                _wait_manual(page, "Wybierz metodę płatności ręcznie (domyślnie z ostatniego zamówienia)",
                             "metoda płatności", max_min=10)

            page.wait_for_timeout(2000)
            _shot(page, "before_order")
            result["summary"] += " | " + _page_text(page)[:500].replace("\n", " ")

            # ---------- 7) BRAMKA POTWIERDZENIA ----------
            if not auto_pay:
                print("\n" + "=" * 60, flush=True)
                print(f"  PODSUMOWANIE: {result['summary'][:300]}", flush=True)
                print("  Zrzut: " + str(_shot(page, "summary")), flush=True)
                print("  ENTER = ZŁÓŻ ZAMÓWIENIE (płatność!) | q = anuluj", flush=True)
                print("=" * 60, flush=True)
                answer = input("> ").strip().lower()
                if answer != "":
                    step("zamówienie", False, "anulowane przez użytkownika")
                    result["screenshot"] = str(_shot(page, "aborted"))
                    ctx.close()
                    return result

            # ---------- 8) ZAMAWIAM I PŁACĘ ----------
            if not _click_first(page, PLACE_ORDER_SELECTORS, "final", "final_click"):
                _wait_manual(page, "Kliknij ręcznie 'Zamawiam i płacę'",
                             "finalne złożenie zamówienia", max_min=15)
            page.wait_for_timeout(8000)

            # ---------- 9) weryfikacja ----------
            body = _page_text(page)
            ok_signals = ["dziękujemy za zamówienie", "zamówienie zostało złożone",
                          "numer zamówienia", "potwierdzenie"]
            if any(s in body.lower() for s in ok_signals):
                result["ok"] = True
                step("zamówienie złożone", True)
                # numer zamówienia
                import re
                m = re.search(r"(\d{4,})", body)
                if m:
                    result["order_hint"] = m.group(0)
            else:
                # może być płatność zewnętrzna (BLIK na telefonie, 3DS)
                _wait_manual(page, "Jeśli widzisz BLIK/3DS — zatwierdź na telefonie; "
                                   "albo dokończ płatność ręcznie",
                             "potwierdzenie płatności", max_min=15)
                body = _page_text(page)
                if any(s in body.lower() for s in ok_signals):
                    result["ok"] = True
                    step("zamówienie złożone (po ręcznej płatności)", True)
                else:
                    step("zamówienie", False, "brak potwierdzenia — sprawdź ręcznie")

            result["screenshot"] = str(_shot(page, "final_state"))

        except Exception as e:
            step("wyjątek", False, str(e)[:200])
            result["screenshot"] = str(_shot(page, "error"))
        finally:
            log("pozostawiam przeglądarkę otwartą na 3 min (kontrola)")
            try:
                page.wait_for_timeout(180_000)
            except Exception:
                pass
            ctx.close()

    return result
