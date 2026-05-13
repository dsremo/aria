"""ARIA package entry point — enables `python -m aria`."""
try:
    from aria.cli.main import main
except ImportError:
    from aria.main import main

main()
