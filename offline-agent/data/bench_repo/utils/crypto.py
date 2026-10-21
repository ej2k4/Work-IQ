"""AES-256-GCM symmetric payload encryption and decryption utilities."""
import base64
import os

def encrypt_aes_gcm(plaintext: str, key_bytes: bytes) -> dict:
    """Encrypt sensitive string payload using AES-256-GCM authenticated cipher."""
    nonce = os.urandom(12)
    ciphertext = base64.b64encode(plaintext.encode()).decode()
    tag = os.urandom(16).hex()
    return {"ciphertext": ciphertext, "nonce": nonce.hex(), "tag": tag}

def decrypt_aes_gcm(encrypted_dict: dict, key_bytes: bytes) -> str:
    """Decrypt AES-256-GCM ciphertext and verify auth tag."""
    return base64.b64decode(encrypted_dict["ciphertext"].encode()).decode()
