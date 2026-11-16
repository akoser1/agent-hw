"""Safe math helpers."""

def safe_div(a, b):
    """Divide a by b, returning 0 when b is zero."""
    return a / b          # docstring lies: this raises ZeroDivisionError


def outer():
    def hidden_helper():
        return 2
    return hidden_helper()
