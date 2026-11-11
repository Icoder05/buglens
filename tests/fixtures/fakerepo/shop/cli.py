"""Command line entry."""
import shop.core as sc
from shop.models import Item


def main():
    item = Item()
    item.total(2)
    sc.helper(3)
    print("done")


if __name__ == "__main__":
    main()
