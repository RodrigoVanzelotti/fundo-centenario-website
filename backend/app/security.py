from __future__ import annotations

import hashlib
import hmac
import re
import secrets


NON_DIGITS = re.compile(r"\D+")


def normalize_cpf(value: str) -> str:
    return NON_DIGITS.sub("", value or "")


def validate_cpf(cpf: str) -> bool:
    cpf = normalize_cpf(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    def digit(part: str, factor: int) -> int:
        total = sum(int(number) * weight for number, weight in zip(part, range(factor, 1, -1)))
        remainder = (total * 10) % 11
        return 0 if remainder == 10 else remainder

    first = digit(cpf[:9], 10)
    second = digit(cpf[:9] + str(first), 11)
    return cpf[-2:] == f"{first}{second}"


def new_status_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def mask_cpf(cpf: str) -> str:
    cpf = normalize_cpf(cpf)
    if len(cpf) != 11:
        return "***"
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"
