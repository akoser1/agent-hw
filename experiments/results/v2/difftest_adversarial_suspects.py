# DiffTest: tests that contradict each other. One side may be catching a BUG in the changed code.
# This file is not collected by pytest. Decide which expectation is right, then fix the code or the test.
from calculator import percent_of


# FAILED: assert 5.0 == 50.0 | contradicts test_percent_of_half_buggy_expectation: possible bug in the changed code
def test_percent_of_half_correct_expectation():
    assert percent_of(1, 2) == 50.0


# CONFLICT: expects a different result than test_percent_of_half_correct_expectation for percent_of(1, 2)
def test_percent_of_half_buggy_expectation():
    assert percent_of(1, 2) == 5.0
