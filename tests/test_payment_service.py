"""
Tests for payment_service — INCOMPLETE test suite.

These tests cover basic scenarios but MISS the critical bug case
where a 100% discount with tax produces a negative total.
"""

import pytest
from src.models import Discount, DiscountType, Order, OrderItem
from src.services.payment_service import (
    calculate_order_total,
    process_payment,
)


class TestCalculateOrderTotal:
    def test_basic_order_no_discount(self):
        items = [OrderItem(name="Widget", quantity=2, unit_price=25.00)]
        result = calculate_order_total(items)
        assert result["subtotal"] == 50.00
        assert result["tax_amount"] == 4.00  # 8% of 50
        assert result["discount_amount"] == 0.0
        assert result["total"] == 54.00

    def test_multiple_items(self):
        items = [
            OrderItem(name="Widget", quantity=1, unit_price=30.00),
            OrderItem(name="Gadget", quantity=2, unit_price=10.00),
        ]
        result = calculate_order_total(items)
        assert result["subtotal"] == 50.00
        assert result["total"] == 54.00

    def test_fixed_discount(self):
        items = [OrderItem(name="Widget", quantity=1, unit_price=100.00)]
        discount = Discount(
            code="SAVE10", discount_type=DiscountType.FIXED, value=10.00
        )
        result = calculate_order_total(items, discount=discount)
        assert result["discount_amount"] == 10.00
        # Note: the test doesn't validate the total is correct —
        # it just checks the discount was applied at all
        assert result["total"] == 98.00  # 108 - 10

    def test_small_percentage_discount(self):
        """Tests a 10% discount — this works fine even with the bug."""
        items = [OrderItem(name="Widget", quantity=1, unit_price=100.00)]
        discount = Discount(
            code="SAVE10", discount_type=DiscountType.PERCENTAGE, value=10.0
        )
        result = calculate_order_total(items, discount=discount)
        # With the bug: gross = 108, discount = 108 * 0.10 = 10.80
        # total = 108 - 10.80 = 97.20
        # This "passes" because the total is still positive — but it's
        # actually computing the wrong amount ($97.20 vs correct $97.20)
        # Coincidentally close for small percentages.
        assert result["total"] > 0

    # MISSING: test_100_percent_discount — this is the case that triggers
    # the bug. A proper test suite would include:
    #
    # def test_100_percent_discount_should_be_zero(self):
    #     items = [OrderItem(name="Widget", quantity=1, unit_price=50.00)]
    #     discount = Discount(
    #         code="FREE100", discount_type=DiscountType.PERCENTAGE, value=100.0
    #     )
    #     result = calculate_order_total(items, discount=discount)
    #     assert result["total"] == 0.00  # WOULD FAIL — returns -$4.00


class TestProcessPayment:
    def test_process_valid_payment(self):
        order = Order(total=54.00)
        result = process_payment(order)
        assert result.success is True
        assert result.amount == 54.00
        assert result.payment_id is not None

    def test_process_zero_payment_raises(self):
        order = Order(total=0.00)
        with pytest.raises(ValueError, match="positive"):
            process_payment(order)

    # MISSING: test_process_negative_payment — not tested because the
    # developer assumed totals are always >= 0
