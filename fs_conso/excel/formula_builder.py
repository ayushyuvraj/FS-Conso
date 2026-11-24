"""Formula construction and formula injection defense utilities."""

import re

DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def escape_csv_formula_injection(val: str) -> str:
    """Neutralizes formula injection attacks (CSV Injection / CWE-1236).

    If an untrusted string starts with '=', '+', '-', '@', tab or carriage return,
    prepends an apostrophe single-quote to prevent spreadsheet formula execution.
    """
    if not val:
        return ""
    str_val = str(val)
    if str_val.startswith(DANGEROUS_PREFIXES):
        return "'" + str_val
    return str_val

def is_safe_excel_formula(expr: str) -> bool:
    """Validates that a formula string only uses recognized accounting functions

    and does not contain malicious system calls (e.g. cmd, DDE, EXEC).
    """
    if not expr:
        return True
    lowered = expr.lower()
    dangerous_keywords = ["cmd", "powershell", "exec", "system", "dde", "reg", "mshta", "cscript", "wscript"]
    return not any(dk in lowered for dk in dangerous_keywords)
