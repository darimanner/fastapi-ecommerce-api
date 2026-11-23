import asyncio
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()

# Verified against for unknown users so login timing does not reveal which emails exist.
DUMMY_HASH = _hasher.hash(secrets.token_urlsafe())


async def hash_password(plain: str) -> str:
    return await asyncio.to_thread(_hasher.hash, plain)


async def verify_password(plain: str, hashed: str) -> bool:
    try:
        return await asyncio.to_thread(_hasher.verify, hashed, plain)
    except VerifyMismatchError, InvalidHashError:
        return False
