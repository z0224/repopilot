import pytest

from inventory.errors import InsufficientStockError
from inventory.repository import InventoryRepository
from inventory.service import reserve_inventory


def test_successful_reservation():
    repository = InventoryRepository({"apple": 10, "banana": 5})

    reserve_inventory(repository, [("apple", 3), ("banana", 2)])

    assert repository.snapshot() == {"apple": 7, "banana": 3}


def test_failed_reservation_is_atomic():
    repository = InventoryRepository({"apple": 10, "banana": 1})

    with pytest.raises(InsufficientStockError):
        reserve_inventory(repository, [("apple", 3), ("banana", 2)])

    assert repository.snapshot() == {"apple": 10, "banana": 1}


def test_duplicate_skus_are_aggregated():
    repository = InventoryRepository({"apple": 5})

    with pytest.raises(InsufficientStockError):
        reserve_inventory(repository, [("apple", 3), ("apple", 3)])

    assert repository.snapshot() == {"apple": 5}


def test_invalid_quantity_does_not_modify_inventory():
    repository = InventoryRepository({"apple": 10, "banana": 5})

    with pytest.raises(ValueError):
        reserve_inventory(repository, [("apple", 3), ("banana", 0)])

    assert repository.snapshot() == {"apple": 10, "banana": 5}


def test_unknown_sku_does_not_modify_inventory():
    repository = InventoryRepository({"apple": 10})

    with pytest.raises(InsufficientStockError):
        reserve_inventory(repository, [("unknown", 1)])

    assert repository.snapshot() == {"apple": 10}
