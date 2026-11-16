"""Real helper code whose file name looks like a test file."""

def test_mode(values):
    """Return the most common value in a non-empty list."""
    return max(set(values), key=values.count)
