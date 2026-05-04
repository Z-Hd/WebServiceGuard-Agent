"""Tiny WSGI-style app with an intentional bug for repair demos."""

from __future__ import annotations

from urllib.parse import parse_qs


def calculate_total_from_query(query_string: str) -> int:
    """Compute an order total from query-string parameters.

    Expected behavior:
    - subtotal is required
    - discount is optional and should default to 0 when omitted

    Current bug:
    - missing discount becomes an empty string, which raises ValueError
    """

    params = parse_qs(query_string)
    subtotal = int(params["subtotal"][0])
    discount_text = params.get("discount", [""])[0]
    discount = int(discount_text)
    return subtotal - discount


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    if path != "/total":
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"not found\n"]

    query_string = environ.get("QUERY_STRING", "")
    total = calculate_total_from_query(query_string)
    body = f"total={total}\n".encode("utf-8")
    start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
    return [body]
