"""Unit tests for EncryptionManager."""
import pytest


def test_password_not_set_initially(isolated_encryption_manager):
    assert isolated_encryption_manager.is_password_set() is False


def test_setup_password_succeeds(isolated_encryption_manager):
    success, msg = isolated_encryption_manager.setup_password("TestPass123!")
    assert success is True


def test_password_is_set_after_setup(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    assert isolated_encryption_manager.is_password_set() is True


def test_verify_correct_password(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    success, msg = isolated_encryption_manager.verify_password("TestPass123!")
    assert success is True


def test_verify_wrong_password_fails(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    success, msg = isolated_encryption_manager.verify_password("WrongPass!")
    assert success is False


def test_verify_wrong_password_does_not_crash(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    try:
        isolated_encryption_manager.verify_password("BadPass")
    except Exception as e:
        pytest.fail(f"verify_password raised unexpectedly: {e}")


def test_encrypt_decrypt_roundtrip(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    isolated_encryption_manager.verify_password("TestPass123!")  # unlock
    plaintext = "Hello, 世界! <b>Bold</b>"
    ciphertext = isolated_encryption_manager.encrypt(plaintext)
    assert ciphertext != plaintext
    recovered = isolated_encryption_manager.decrypt(ciphertext)
    assert recovered == plaintext


def test_pbkdf2_iterations(isolated_encryption_manager):
    assert isolated_encryption_manager.ITERATIONS >= 100000


def test_lock_clears_key(isolated_encryption_manager):
    isolated_encryption_manager.setup_password("TestPass123!")
    isolated_encryption_manager.verify_password("TestPass123!")
    assert isolated_encryption_manager.is_unlocked is True
    isolated_encryption_manager.lock()
    assert isolated_encryption_manager.is_unlocked is False
