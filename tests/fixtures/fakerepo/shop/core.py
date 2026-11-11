"""Core utilities used everywhere."""

RATE = 3


def helper(x):
    """Double a value."""
    return x * 2


class Base:
    """Base model."""

    def save(self):
        return helper(1)
