import re
from datetime import date


def parse_month(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("month must use YYYY-MM format")
    parsed = date.fromisoformat(f"{value}-01")
    if parsed.day != 1:
        raise ValueError("month must use YYYY-MM format")
    return parsed
