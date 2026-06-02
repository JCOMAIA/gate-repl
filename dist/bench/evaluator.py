import re


_FINAL = re.compile(r"FINAL\s*:\s*R?\$?\s*([\-\d.,]+)", re.IGNORECASE)
_NUMBER = re.compile(r"[\-]?\d[\d.,]*")
_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*.*?\s*```", re.DOTALL)


def _strip_code_blocks(text: str) -> str:
    return _CODE_BLOCK.sub("", text)


def _parse_number(raw: str) -> float | None:
    raw = raw.strip().rstrip(".,")
    if not raw:
        return None
    has_dot = "." in raw
    has_comma = "," in raw
    try:
        if has_dot and has_comma:
            # whichever appears last is the decimal separator
            last_dot = raw.rfind(".")
            last_comma = raw.rfind(",")
            if last_comma > last_dot:
                cleaned = raw.replace(".", "").replace(",", ".")
            else:
                cleaned = raw.replace(",", "")
        elif has_comma and not has_dot:
            # one comma with <=2 trailing digits -> decimal comma
            parts = raw.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                cleaned = raw.replace(",", ".")
            else:
                cleaned = raw.replace(",", "")
        else:
            cleaned = raw
        return float(cleaned)
    except ValueError:
        return None


def extract_final_number(text: str) -> float | None:
    if not text:
        return None
    text = _strip_code_blocks(text)
    # Use the LAST FINAL: — when a model self-corrects, its final commitment
    # is the last one it writes, not the first (which may be a discarded guess).
    finals = list(_FINAL.finditer(text))
    for m in reversed(finals):
        v = _parse_number(m.group(1))
        if v is not None:
            return v
    # fallback: last number in the text
    nums = _NUMBER.findall(text)
    for raw in reversed(nums):
        v = _parse_number(raw)
        if v is not None:
            return v
    return None


def matches(value: float | None, target: float, tol: float = 0.01) -> bool:
    return value is not None and abs(value - target) <= tol


# --- belief-aware outcome classification ---

_ABSTAIN = re.compile(
    r"\b(INSUFFICIENT|NOT ENOUGH|CANNOT (?:COMPUTE|ANSWER|DETERMINE)|"
    r"INSUFICIENTE|N[ÃA]O (?:TENHO|POSSO|É POSS[IÍ]VEL)|DADOS? FALTANDO|"
    r"MISSING DATA|GAP)\b",
    re.IGNORECASE,
)

# Matches the LACUNA section of a belief reconstruction and captures its body
# up to the next ALL-CAPS section header or end of text.
_LACUNA = re.compile(r"LACUNA\s*:?\s*(.*?)(?:\n[A-ZÇÃ]{4,}\s*:|\Z)", re.IGNORECASE | re.DOTALL)
_LACUNA_EMPTY = re.compile(r"^\W*(nenhuma|vazi[oa]|none|n/?a|-|—|sem lacuna)\W*$", re.IGNORECASE)


def _lacuna_signals_gap(text: str) -> bool:
    """True if a LACUNA section exists AND is not declared empty."""
    m = _LACUNA.search(text)
    if not m:
        return False
    body = m.group(1).strip()
    if not body:
        return False
    first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    return not _LACUNA_EMPTY.match(first)


def classify_outcome(
    output: str, target: float, tol: float = 0.01, context_sufficient: bool | None = None
) -> str:
    """Classify a response into mutually exclusive outcomes.

    CORRECT        — emits the right number
    ABSTENTION     — acknowledges a gap (keyword or non-empty LACUNA) and does
                     NOT commit a final number  (honest epistemic failure)
    CONFABULATION  — commits a wrong number when context was INSUFFICIENT
                     (acted on a false belief about its information state)
    ARITHMETIC_FAIL— commits a wrong number when context was SUFFICIENT
                     (had the data, knew it, miscomputed — a compute problem,
                     not a belief problem; the RLM/REPL's job, not RAG's)
    OTHER          — none of the above

    `context_sufficient` splits the two wrong-number failure modes. When None,
    any committed wrong number is labeled CONFABULATION (legacy behavior).
    """
    text = _strip_code_blocks(output or "")
    value = extract_final_number(output)
    if matches(value, target, tol):
        return "CORRECT"

    committed = _FINAL.search(text) is not None
    gap_ack = bool(_ABSTAIN.search(text)) or _lacuna_signals_gap(text)

    if not committed and gap_ack:
        return "ABSTENTION"
    if committed or value is not None:
        if context_sufficient is True:
            return "ARITHMETIC_FAIL"
        return "CONFABULATION"
    return "OTHER"


def matches(value: float | None, target: float, tol: float = 0.01) -> bool:
    return value is not None and abs(value - target) <= tol
