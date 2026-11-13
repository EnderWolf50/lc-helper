"""lc-helper.exe's entry point for PyInstaller (src/lc_helper/__main__.py uses a relative import, which a frozen
script cannot)."""

from lc_helper.app import main

main()
