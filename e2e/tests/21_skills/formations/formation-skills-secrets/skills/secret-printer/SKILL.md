---
name: secret-printer
description: "Print a greeting message using a secret value. Use when asked to print a greeting."
---

# Secret Printer

This skill prints a greeting sourced from a secret.

The greeting value is: ${{ secrets.SKILL_TEST_GREETING }}

## Instructions

1. Run `scripts/print_greeting.py` using the run_skill tool
2. Return the output to the user
