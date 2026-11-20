"""Stage S5 label-noise filter: payload signatures (Appendix A of the paper).

A record labeled Normal whose twice URL-decoded input string matches a CORE
signature carries an attack payload, which contradicts its label, so S5 removes it.
PROBE signatures mark scanner probes outside the nine classes. They are reported
but kept in Normal (paper setting, mode "core").
"""
from __future__ import annotations

import re
import urllib.parse as up

SIGNATURES_CORE = {
    "OS command": r"(?:&&|\|\||`|\$\(|;|\|)\s*(?:cat|sleep|ping|id|whoami|uname|ls|echo)\b"
                  r"|/etc/passwd|/bin/(?:sh|bash|sleep)|\(\)\s*\{",
    "SQL": r"union\s+(?:all\s+)?select|sleep\(\d|\bor\s+'?1'?\s*=|waitfor\s+delay"
           r"|benchmark\(|\bselect\b.+\bfrom\b|\band\s+\d+\s*=\s*\d+|order\s+by\s+\d+\s*#",
    "Path traversal": r"\.\./|\.\.\\",
    "Script injection": r"<script|alert\(|onerror\s*=|javascript:",
}
SIGNATURES_PROBE = {
    "Server-side include": r"<!--\s*#\s*exec",
    "Open redirect or remote inclusion": r"owasp\.org|\d;\s*url\s*=",
    "Markup fuzzing": r"<!--|\]\]>",
    "Fuzzing characters": r"\x00|[|'\"`<>;]",
}
_CORE = [(k, re.compile(v, re.I)) for k, v in SIGNATURES_CORE.items()]
_PROBE = [(k, re.compile(v, re.I)) for k, v in SIGNATURES_PROBE.items()]


def decode_twice(text: str) -> str:
    return up.unquote_plus(up.unquote_plus(str(text)))


def payload_type(text: str, which: str = "core") -> str | None:
    """Name of the first matching signature group, checked in the order above, or None."""
    decoded = decode_twice(text)
    groups = {"core": _CORE, "probe": _PROBE, "all": _CORE + _PROBE}[which]
    for name, rx in groups:
        if rx.search(decoded):
            return name
    return None
