from discount import apply_discount, is_eligible


def test_apply_discount_runs():
    assert isinstance(apply_discount(100, 10), float)
    assert isinstance(apply_discount(100, -5), float)    # exercises pct<0 clamp
    assert isinstance(apply_discount(100, 150), float)   # exercises pct>100 clamp


def test_is_eligible_runs():
    assert isinstance(is_eligible(70, True), bool)
    assert isinstance(is_eligible(60, False), bool)
