"""Shop models."""
from . import core
from .core import Base, helper


class Item(Base):
    """A sellable item."""

    price = 10

    def total(self, qty):
        return helper(qty) * self.price

    def describe(self):
        self.total(1)
        core.helper(2)
        return unknown_func()
