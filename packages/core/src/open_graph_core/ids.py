import secrets
import time
from uuid import UUID

PREFIXES = frozenset({"proj", "ds", "doc", "chunk", "ent", "rel", "job", "qry"})


def uuid7() -> UUID:
    ms = int(time.time() * 1000)
    value = (
        (ms << 80)
        | (0x7 << 76)
        | (secrets.randbits(12) << 64)
        | (0b10 << 62)
        | secrets.randbits(62)
    )
    return UUID(int=value)


def new_id(prefix: str) -> str:
    if prefix not in PREFIXES:
        raise ValueError(f"unsupported resource prefix: {prefix}")
    return f"{prefix}_{uuid7()}"
