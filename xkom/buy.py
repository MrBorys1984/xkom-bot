"""
Pełny zakup: produkt -> kod -> kasa -> ZAMÓWIENIE.

Przykłady:
  python3 -m xkom.buy "https://www.x-kom.pl/p/1520216-...html" --code A2C3E4L
  python3 -m xkom.buy "https://www.x-kom.pl/p/1520216-...html" --code A2C3E4L --pay
  python3 -m xkom.buy "https://www.x-kom.pl/p/1520216-...html"          # bez kodu

--pay  = pełna automatyzacja: bot kliknie "Zamawiam i płacę" BEZ ENTERa
         (domyślnie: bot staje przed finalnym kliknięciem i czeka na ENTER)
"""
import argparse
import json
import sys

from .common import log
from .checkout import run_checkout


def main():
    ap = argparse.ArgumentParser(description="Silnik zakupów x-kom")
    ap.add_argument("product_url", help="URL produktu")
    ap.add_argument("--code", help="kod rabatowy do użycia w koszyku")
    ap.add_argument("--pay", action="store_true",
                    help="skocz potwierdzenie ENTER — kliknij 'Zamawiam i płacę' od razu")
    ap.add_argument("--expect-low-price", action="store_true",
                    help="ostrzegaj, jeśli cena po rabacie nie jest ~1 zł")
    ap.add_argument("--headless", action="store_true",
                    help="bez okna (tylko do testów — nie zalecane)")
    args = ap.parse_args()

    log(f"START ZAKUPU: {args.product_url} kod={args.code} auto_pay={args.pay}")
    res = run_checkout(args.product_url, code=args.code,
                       auto_pay=args.pay, headless=args.headless,
                       expect_price_low=args.expect_low_price)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
