# Security Policy

## Supported Versions

Security updates and vulnerability fixes are focused on the active mainline bring-up branch.

| Version / Branch | Supported          |
| ---------------- | ------------------ |
| `main`           | :white_check_mark: |
| Historical tags  | :x:                |

## Reporting a Vulnerability

We take the security of the Allwinner H713 mainline firmware, boot chain (U-Boot SPL, TF-A BL31, U-Boot proper), signed rootfs verification, and kernel components seriously.

If you believe you have found a security vulnerability:

1. **GitHub Private Vulnerability Reporting (Preferred)**:
   - Please report the issue confidentially using GitHub's Private Vulnerability Reporting under the [Security tab](https://github.com/cstenger/allwinner-h713-mainline/security).

2. **Email**:
   - If you cannot use GitHub's vulnerability reporting, please email:
     `christopher.h.stenger@gmail.com`
   - Please include:
     - Component affected (e.g., TF-A BL31, U-Boot SPL, signed rootfs keys/verification, serial loader, Debian rootfs image)
     - Target hardware variant (`HY200_QZ713DF_A1` bench board or `HY200_QZ713_V2` projector board)
     - A detailed description of the vulnerability and steps or proof-of-concept to reproduce it.

Please do not disclose security vulnerabilities publicly in GitHub Issues or Discussions until they have been reviewed and addressed.
