from warframe_routes.effort import rotation_factor


def test_generic_modes_use_aabc_cadence():
    # Defense/Survival/Excavation/etc.: A is the 1st drop, B the 3rd, C the 4th.
    assert rotation_factor("A", "Survival") == 1.0
    assert rotation_factor("B", "Survival") == 3.0
    assert rotation_factor("C", "Survival") == 4.0
    assert rotation_factor(None, "Capture") == 1.0


def test_disruption_does_not_use_aabc_cadence():
    # wiki.warframe.com/w/Disruption: defending all 4 conduits every round
    # reaches Rotation B after round 1 and Rotation C after round 3 -- not
    # the "3x"/"4x" a generic endless mode's AABC table would imply.
    assert rotation_factor("A", "Disruption") == 1.0
    assert rotation_factor("B", "Disruption") == 1.0
    assert rotation_factor("C", "Disruption") == 3.0


def test_disruption_factor_is_lower_than_generic_for_b_and_c():
    assert rotation_factor("B", "Disruption") < rotation_factor("B", "Survival")
    assert rotation_factor("C", "Disruption") < rotation_factor("C", "Survival")


def test_unknown_mode_falls_back_to_generic_table():
    assert rotation_factor("C", "SomeFutureMode") == rotation_factor("C", "Survival")


def test_mode_omitted_falls_back_to_generic_table():
    assert rotation_factor("C") == 4.0
