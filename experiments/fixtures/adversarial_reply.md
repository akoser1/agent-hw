Offline reply for the adversarial run. percent_of has an injected bug (* 10 instead of * 100).
One test asserts the buggy value, one asserts the correct value.

```python
from calculator import percent_of


def test_percent_of_half_buggy_expectation():
    assert percent_of(1, 2) == 5.0


def test_percent_of_half_correct_expectation():
    assert percent_of(1, 2) == 50.0
```
