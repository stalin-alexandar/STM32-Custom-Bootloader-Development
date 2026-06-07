"""
Entry point for running the bootloader host as a module: python -m bootloader_host
"""

import sys
from .cli import main

sys.exit(main())
