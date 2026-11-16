"""Create greeting messages for users."""

class Greeter:
    """Produce a greeting for a given name."""
    def greet(self, name, excited=False):
        """Return a friendly greeting. Strips whitespace; rejects empty names."""
        name = name.strip()
        if not name:
            raise ValueError('name must not be empty')
        return f'Hello, {name}' + ('!!!' if excited else '!')
