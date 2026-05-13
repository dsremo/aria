"""Generate the boot manifest at release time.

Usage::

    python -m aria.boot.generate_manifest > data/sealed/BOOT_MANIFEST.toml

This walks src/aria/{cognitive,safety,monitor,agents}/, hashes every
.py with SHA-256, and renders TOML the verifier (aria.boot.verify)
parses at boot.

Run this whenever a release-engineer is cutting a new image. The
output should then be signed (Ed25519 → ML-DSA when PQC HSM ships)
before being baked into the immutable boot image.
"""

import sys

from aria.boot.verify import render_manifest_toml


def main() -> int:
    sys.stdout.write(render_manifest_toml())
    return 0


if __name__ == "__main__":
    sys.exit(main())
