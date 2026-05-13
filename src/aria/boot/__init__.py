"""Boot-time integrity verification (F-18).

Guards the safety-critical Python tree against tamper. The verifier
walks a fixed set of paths (cognitive/, safety/, monitor/, agents/),
recomputes SHA-256 of every .py file, and compares to the boot
manifest. Any mismatch refuses to start.

This is the software side of the §F-18 contract. The hardware side
(TPM-anchored measured boot, SLSA-grade build provenance) is out of
software scope but *must* exist in production deployments.

Used as the first thing in __main__:

    from aria.boot import verify_boot_integrity
    verify_boot_integrity()  # exits 87 on mismatch

Genrate the manifest at release time:

    python -m aria.boot.generate_manifest > data/sealed/BOOT_MANIFEST.toml
"""

from aria.boot.verify import verify_boot_integrity, BootIntegrityError

__all__ = ["verify_boot_integrity", "BootIntegrityError"]
