"""The unit under test: a tiny pricing module with real branching logic."""


def apply_discount(price, pct):
    """price after a pct% discount, with pct clamped to [0, 100]."""
    if pct < 0:
        pct = 0
    if pct > 100:
        pct = 100
    return price * (1 - pct / 100)


def is_eligible(age, member):
    """The senior-member rate: 65 or older AND a member."""
    return age >= 65 and member
