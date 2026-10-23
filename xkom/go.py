"""
SYGNAŁ GO — zastosuj kod w koszyku x-kom TERAZ.

Przykłady:
  python3 -m xkom.go XKOM-9F2KQ1
  python3 -m xkom.go 482913 --product "https://www.x-kom.pl/p/1520216-...html"
  python3 -m xkom.go 482913 --search "HyperX Cloud Mini"
"""
import argparse
import json
import sys

from .common import log
from .apply import apply_code


def main():
    ap = argparse.ArgumentParser(description="Zastosuj kod rabatowy w x-kom")
    ap.add_argument("code", help="kod rabatowy")
    ap.add_argument("--product", help="URL produktu do dodania do koszyka")
    ap.add_argument("--search", help="fraza szukajki produktu (jeśli nie znasz URL-a)")
    ap.add_argument("--headless", action="store_true", help="bez okna przeglądarki (nie zalecane)")
    args = ap.parse_args()

    log(f"GO! Kod: {args.code}")
    res = apply_code(args.code, product_url=args.product,
                     product_search=args.search, headless=args.headless)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
