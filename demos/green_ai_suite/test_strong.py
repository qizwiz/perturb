from discount import apply_discount, is_eligible


def test_apply_discount_value():
    assert apply_discount(100, 10) == 90.0     # kills  * -> +  and  1-x -> 1+x
    assert apply_discount(100, -5) == 100.0    # kills the pct<0 clamp mutation
    assert apply_discount(100, 150) == 0.0     # kills the pct>100 clamp mutation


def test_is_eligible_logic():
    assert is_eligible(70, True) is True
    assert is_eligible(64, True) is False      # kills  >= -> >
    assert is_eligible(70, False) is False     # kills  and -> or
