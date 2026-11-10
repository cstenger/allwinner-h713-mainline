#!/usr/bin/env python3
"""WITHDRAWN: the U-Boot RAM table is read-only; this tool always refuses.

The first hardware write caused a permission abort. The historical prototype
is archived as text under docs/audio-trace-diagnostics/. Do not retry it.
"""
import sys


def main():
    sys.exit("RAM installation withdrawn: first write caused a permission abort; no device opened or writes attempted.")


if __name__ == "__main__":
    main()
