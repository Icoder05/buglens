"""Invoices."""
from shop import models
from shop.core import Base, helper


class Invoice(models.Item):
    """An invoice is an item."""

    def amount(self):
        self.total(1)
        return helper(self.price)


class Receipt(Base):
    def amount(self):
        return 0
