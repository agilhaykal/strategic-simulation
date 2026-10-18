"""Conservative outbound minimization. This is not a compliance certification."""
import re

PATTERNS = [
    re.compile(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', re.I),
    re.compile(r'(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)'),
    re.compile(r'\b(?:sk-or-v1-|sk-)[A-Za-z0-9_-]{12,}\b'),
    re.compile(r'(?i)\b(?:password|api[_ ]?key|token)\s*[:=]\s*[^\s,;]+'),
]
IDENTIFIER = re.compile(r'(?i)(?:^|_)(?:id|uuid|key|identifier|nik|ktp|npwp|email|phone|telephone|mobile|address|alamat|name|nama|dob|birth|ssn|iban|account|rekening|plate|license|vin|passport|customer_id|nasabah_id)(?:_|$)')

def scrub(text):
    for pattern in PATTERNS:
        text = pattern.sub(lambda m: '[REDACTED]' if pattern is not PATTERNS[1] or sum(c.isdigit() for c in m.group()) >= 10 else m.group(), str(text))
    return text

def contains_pii(value):
    return any(any(p is not PATTERNS[1] or sum(c.isdigit() for c in m.group()) >= 10 for m in p.finditer(str(value))) for p in PATTERNS)

def sensitive_header(header):
    normalized = re.sub(r'[^a-z0-9]+', '_', re.sub(r'([a-z])([A-Z])', r'\1_\2', header).lower())
    return bool(IDENTIFIER.search(normalized) or contains_pii(header))

def outbound(value):
    if isinstance(value, str): return scrub(value)
    if isinstance(value, list): return [outbound(x) for x in value]
    if isinstance(value, dict): return {scrub(k): outbound(v) for k,v in value.items()}
    return value
