"""Money helpers — all amounts are integer minor units (paise).

Rules enforced here (see docs/ACCOUNTING_RULES.md):
  * no binary floating point on any financial path
  * half-up rounding at the currency minor unit
  * largest-remainder allocation so parts always sum to the whole
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

MINOR = Decimal("0.01")


class MoneyError(ValueError):
    pass


def parse_amount(value) -> int:
    """Parse a user/API amount into integer paise. Rejects float and >2 dp input."""
    if isinstance(value, bool):
        raise MoneyError("amount must be a number")
    if isinstance(value, float):
        raise MoneyError("float is not allowed for money; send a string or integer paise")
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "").replace("\u20b9", "")
    if not text:
        raise MoneyError("amount is empty")
    try:
        dec = Decimal(text)
    except InvalidOperation as exc:
        raise MoneyError(f"invalid amount: {value!r}") from exc
    if not dec.is_finite():
        raise MoneyError("amount must be finite")
    q = dec.quantize(MINOR, rounding=ROUND_HALF_UP)
    if q != dec:
        raise MoneyError(f"amount has more than 2 decimal places: {value!r}")
    return int(q * 100)


def parse_qty(value) -> int:
    """Quantity with 3 decimals, stored as thousandths."""
    if isinstance(value, float):
        raise MoneyError("float quantity is not allowed; send a string")
    text = str(value).strip()
    try:
        dec = Decimal(text)
    except InvalidOperation as exc:
        raise MoneyError(f"invalid quantity: {value!r}") from exc
    q = dec.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    if q != dec:
        raise MoneyError("quantity has more than 3 decimal places")
    return int(q * 1000)


def parse_percent(value) -> int:
    """Parse a percentage into basis points (18% -> 1800, 18.5% -> 1850)."""
    if isinstance(value, float):
        raise MoneyError("float percentage is not allowed; send a string")
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text:
        return 0
    try:
        dec = Decimal(text)
    except InvalidOperation as exc:
        raise MoneyError(f"invalid percentage: {value!r}") from exc
    q = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if q != dec:
        raise MoneyError(f"percentage has more than 2 decimal places: {value!r}")
    if q < 0 or q > 10000:
        raise MoneyError("percentage must be between 0 and 10000")
    return int(q * 100)


def mul_qty_price(qty_milli: int, price_paise: int) -> int:
    """qty(3dp) x price(2dp) -> paise, half-up."""
    if qty_milli < 0 or price_paise < 0:
        raise MoneyError("negative quantity or price")
    return (qty_milli * price_paise + 500) // 1000


def tax_on(base_paise: int, rate_bp: int) -> int:
    """base * rate(basis points) half-up. 1800 bp = 18%."""
    if base_paise < 0 or rate_bp < 0:
        raise MoneyError("negative base or rate")
    return (base_paise * rate_bp + 5000) // 10000


def split_tax(tax_paise: int) -> tuple[int, int]:
    """Split into (cgst, sgst) without losing a paisa."""
    cgst = tax_paise // 2
    return cgst, tax_paise - cgst


def allocate(total_paise: int, weights: list[int]) -> list[int]:
    """Largest-remainder allocation. Sum(result) == total_paise exactly."""
    if not weights:
        return []
    if any(w < 0 for w in weights):
        raise MoneyError("negative weight")
    total_w = sum(weights)
    if total_w == 0:
        weights = [1] * len(weights)
        total_w = len(weights)
    base, rem = divmod(total_paise, total_w)
    parts = [base * w for w in weights]
    remainders = [(total_paise * w) % total_w for w in weights]
    left = total_paise - sum(parts)
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for i in order[:left]:
        parts[i] += 1
    return parts


def fmt(paise: int, symbol: str = "\u20b9") -> str:
    """Indian-grouped display string. 1234567 paise -> ₹12,345.67"""
    neg = paise < 0
    paise = abs(paise)
    rupees, p = divmod(paise, 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{'-' if neg else ''}{symbol}{s}.{p:02d}"


def to_str(paise: int) -> str:
    """Plain decimal string for storage in JSON/exports."""
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    return f"{sign}{paise // 100}.{paise % 100:02d}"


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
         "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _indian(n: int) -> str:
    crore, rest = divmod(n, 10_000_000)
    lakh, rest = divmod(rest, 100_000)
    thousand, rest = divmod(rest, 1_000)
    hundred, rest = divmod(rest, 100)
    parts: list[str] = []
    if crore:
        parts.append(f"{_indian(crore)} Crore")
    if lakh:
        parts.append(f"{_two(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two(thousand)} Thousand")
    if hundred:
        parts.append(f"{_ONES[hundred]} Hundred")
    if rest:
        parts.append(_two(rest))
    return " ".join(parts)


def amount_in_words(paise: int) -> str:
    """Indian-system words for an invoice amount, e.g. 12345678 -> 'One Lakh Twenty Three Thousand...'."""
    if paise < 0:
        return "Minus " + amount_in_words(-paise)
    rupees, paise_part = divmod(paise, 100)
    if rupees == 0 and paise_part == 0:
        return "Zero Rupees Only"
    parts: list[str] = []
    if rupees:
        parts.append(f"{_indian(rupees)} {'Rupee' if rupees == 1 else 'Rupees'}")
    if paise_part:
        parts.append(f"{_two(paise_part)} Paise")
    return " and ".join(parts) + " Only"
