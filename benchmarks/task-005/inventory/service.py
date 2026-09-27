from inventory.errors import InsufficientStockError


def reserve_inventory(repository, items):
    """Reserve a list of (sku, quantity) items."""
    requested = {}
    for sku, quantity in items:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        requested[sku] = requested.get(sku, 0) + quantity

    available = {}
    for sku, quantity in requested.items():
        available[sku] = repository.available(sku)
        if available[sku] < quantity:
            raise InsufficientStockError(sku)

    for sku, quantity in requested.items():
        repository.set_available(sku, available[sku] - quantity)
