"""Generate a SHA-256 hash of an API key for config.yaml, so the plaintext
key never has to live in a config file -- only its hash does.

Usage:
    python -m scripts.hash_api_key
    (paste/type the key when prompted, or pass it as an argument)

Then in config.yaml:
    api:
      keys:
        - key_hash: "<printed hash>"
          scopes: [upload, query, read]
          tenant_id: acme-bank
"""
from __future__ import annotations

import getpass
import sys

from settings import hash_api_key


def main() -> None:
    if len(sys.argv) > 1:
        plaintext = sys.argv[1]
    else:
        plaintext = getpass.getpass("API key to hash (input hidden): ")

    if not plaintext:
        raise SystemExit("No key provided.")

    print(hash_api_key(plaintext))


if __name__ == "__main__":
    main()
