"""Provide basic calculator operations."""

def add(a, b):
    """Return the sum of two numbers."""
    return a + b

def divide(a, b):
    """Divide a by b, rejecting zero divisors and non-numeric input."""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError('divide expects numbers')
    if b == 0:
        raise ValueError('Cannot divide by zero')
    return a / b

def mean(values):
    """Return the average of a non-empty list of numbers."""
    if not values:
        raise ValueError('mean of empty list')
    return sum(values) / len(values)

def percent_of(part, whole):
    """Return part as a percentage of whole, rounded to 1 decimal place."""
    return round(divide(part, whole) * 100, 1)
