Canned LLM reply for an offline run against the shared testbed (bash reset_testbed.sh).
The last three tests are deliberately bad, one per failure mode.

```python
import pytest
from calculator import add, divide, mean, percent_of
from greeter import Greeter


def test_divide_rejects_non_numeric():
    with pytest.raises(TypeError):
        divide("1", 2)


def test_mean_basic_and_single_value():
    assert mean([1, 2, 3, 4]) == 2.5
    assert mean([7]) == 7


def test_mean_empty_list_raises():
    with pytest.raises(ValueError):
        mean([])


def test_percent_of_rounds_to_one_decimal():
    assert percent_of(1, 3) == 33.3


def test_percent_of_zero_whole_raises():
    with pytest.raises(ValueError):
        percent_of(5, 0)


def test_greet_strips_whitespace_and_excited():
    assert Greeter().greet("  Ada  ") == "Hello, Ada!"
    assert Greeter().greet("Ada", excited=True) == "Hello, Ada!!!"


def test_greet_blank_name_raises():
    with pytest.raises(ValueError):
        Greeter().greet("   ")


def test_percent_of_wrong_expectation():
    assert percent_of(1, 3) == 33.33        # failure mode 1: fails (real answer is 33.3)


def test_placeholder():
    mean([1])
    assert True                             # failure mode 2: useless


def test_add_again():
    assert add(2, 3) == 5                   # failure mode 3: repeats tests/test_calculator.py::test_add
```
