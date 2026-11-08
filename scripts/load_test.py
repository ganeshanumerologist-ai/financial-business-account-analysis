"""Small stdlib load test for the ARTHIVIO demo.

Each simulated user logs in once, then reads a fixed set of pages and one CSV
export. The test is read-only: it never posts an invoice, journal or payment.

Usage:
    python scripts/load_test.py --users 20 --requests 5
    python scripts/load_test.py --base http://127.0.0.1:8010 --users 10
"""
from __future__ import annotations

import argparse
import http.cookiejar
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

PAGES = [
    "/",
    "/reports/library",
    "/invoices",
    "/bills",
    "/reports/trial-balance",
    "/export/trial-balance.csv",
]


def one_session(base: str, email: str, password: str, requests: int) -> tuple[list[float], list[str]]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    latencies: list[float] = []
    errors: list[str] = []

    body = urllib.parse.urlencode({"email": email, "password": password}).encode()
    started = time.perf_counter()
    try:
        with opener.open(urllib.request.Request(
                base + "/login", data=body, method="POST"), timeout=30) as response:
            response.read()
            if response.status >= 400:
                errors.append(f"login HTTP {response.status}")
    except (urllib.error.URLError, OSError) as exc:
        errors.append(f"login {exc}")
        return latencies, errors
    latencies.append(time.perf_counter() - started)

    for _ in range(max(1, requests)):
        for path in PAGES:
            started = time.perf_counter()
            try:
                with opener.open(base + path, timeout=30) as response:
                    response.read()
                    if response.status >= 400:
                        errors.append(f"{path} HTTP {response.status}")
            except (urllib.error.URLError, OSError) as exc:
                errors.append(f"{path} {exc}")
            latencies.append(time.perf_counter() - started)

    return latencies, errors


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only ARTHIVIO load test")
    parser.add_argument("--base", default="http://127.0.0.1:8010")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--requests", type=int, default=3,
                        help="page loops per simulated user")
    parser.add_argument("--email", default="owner@arthivio.test")
    parser.add_argument("--password", default="ArthivioDemo!2026")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    users = max(1, args.users)
    started = time.perf_counter()
    latencies: list[float] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=users) as pool:
        futures = [pool.submit(one_session, base, args.email, args.password, args.requests)
                   for _ in range(users)]
        for future in as_completed(futures):
            session_latencies, session_errors = future.result()
            latencies.extend(session_latencies)
            errors.extend(session_errors)

    elapsed = time.perf_counter() - started
    total = len(latencies)
    print(f"Base: {base}")
    print(f"Users: {users}  Page loops per user: {args.requests}  Requests measured: {total}")
    print(f"Elapsed: {elapsed:.2f} s  Throughput: {total / elapsed:.1f} req/s")
    if latencies:
        print(f"Latency mean: {statistics.mean(latencies) * 1000:.1f} ms")
        print(f"Latency p50:  {percentile(latencies, 0.50) * 1000:.1f} ms")
        print(f"Latency p95:  {percentile(latencies, 0.95) * 1000:.1f} ms")
        print(f"Latency p99:  {percentile(latencies, 0.99) * 1000:.1f} ms")
        print(f"Latency max:  {max(latencies) * 1000:.1f} ms")
    print(f"Errors: {len(errors)}")
    for error in errors[:10]:
        print(f"  {error}")
    print("RESULT:", "PASS" if not errors else "FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
