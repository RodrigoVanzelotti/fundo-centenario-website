"""HTTP smoke check: never creates payments, writes donor data or sends email."""
import argparse
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    headers = {"Authorization": "Bearer " + os.environ["SMOKE_ID_TOKEN"]} if os.getenv("SMOKE_ID_TOKEN") else {}
    for path in ("/api/health", "/api/ready", "/", "/como-apoiar/", "/api/donations/options"):
        with urlopen(Request(base + path, headers=headers), timeout=20) as response:
            assert response.status == 200, path
            assert response.headers["X-Content-Type-Options"] == "nosniff", path
            if path.startswith("/api/"):
                assert response.headers["Cache-Control"] == "no-store", path
            else:
                assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"], path
            if args.production:
                assert response.headers.get("Strict-Transport-Security"), path
            if path == "/api/donations/options" and args.production:
                assert json.load(response)["methods"] == ["pix", "card", "card_recurring"]
    for path in ("/backend/.env", "/backend/data/confirmed_donations.jsonl") + (("/openapi.json", "/api/docs") if args.production else ()):
        try:
            urlopen(Request(base + path, headers=headers), timeout=20).close()
        except HTTPError as error:
            assert error.code == 404, path
        else:
            raise AssertionError("Unexpected public resource: " + path)
    print("HTTP smoke check passed")


if __name__ == "__main__":
    main()
