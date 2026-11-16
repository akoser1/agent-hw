"""Provide basic calculator operations."""

def add(a, b):
    """Return the sum of two numbers."""
    return a + b

def divide(a, b):
    """Divide a by b, rejecting zero divisors."""
    if b == 0:
        raise ValueError('Cannot divide by zero')
    return a / b
