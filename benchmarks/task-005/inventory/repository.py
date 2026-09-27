class InventoryRepository:
    def __init__(self, stock):
        self._stock = dict(stock)

    def available(self, sku):
        return self._stock.get(sku, 0)

    def set_available(self, sku, quantity):
        self._stock[sku] = quantity

    def snapshot(self):
        return dict(self._stock)
