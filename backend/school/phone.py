import re


def normalise_kenyan_phone(raw):
    """Turns 07XX..., 2547XX..., +2547XX..., or 7XX... into +2547XXXXXXXX. Returns None if invalid."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("254"):
        return "+" + digits
    if len(digits) == 10 and digits.startswith("0"):
        return "+254" + digits[1:]
    if len(digits) == 9:
        return "+254" + digits
    return None