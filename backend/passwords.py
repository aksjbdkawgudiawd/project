"""Versioned, bounded scrypt hashes for demo wholesale password access."""
import hashlib
import hmac
import secrets


def parse_password_hash(encoded):
    try:
        version, salt_hex, digest_hex = encoded.split("$")
        if version != "scrypt-v1" or len(salt_hex) != 32 or len(digest_hex) != 64:
            return None
        salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if len(salt) != 16 or len(digest) != 32:
            return None
        return salt, digest
    except (ValueError, AttributeError):
        return None


def derive_password(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, dklen=32, maxmem=64 * 1024 * 1024)


def hash_password(password):
    if not 12 <= len(password) <= 256:
        raise ValueError("Password must contain 12–256 characters")
    salt = secrets.token_bytes(16)
    return f"scrypt-v1${salt.hex()}${derive_password(password, salt).hex()}"


def verify_password(password, encoded):
    parsed = parse_password_hash(encoded)
    if parsed is None or not 1 <= len(password) <= 256:
        return False
    salt, expected = parsed
    return hmac.compare_digest(derive_password(password, salt), expected)


if __name__ == "__main__":
    from getpass import getpass

    print(hash_password(getpass("Wholesale demo password (12–256 characters): ")))
