from ecommerce.core.security.passwords import DUMMY_HASH, hash_password, verify_password


async def test_hash_verifies_only_the_original_password() -> None:
    hashed = await hash_password("correct horse")

    assert hashed != "correct horse"
    assert await verify_password("correct horse", hashed)
    assert not await verify_password("wrong horse", hashed)


async def test_garbage_hash_does_not_verify() -> None:
    assert not await verify_password("anything", "not-an-argon2-hash")


async def test_dummy_hash_is_a_real_hash_that_rejects_guesses() -> None:
    assert DUMMY_HASH.startswith("$argon2id$")
    assert not await verify_password("", DUMMY_HASH)
