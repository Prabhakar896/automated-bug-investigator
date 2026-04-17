import sys
import pytest
sys.path.insert(0, '.')

from src.models import OrderItem, Discount, DiscountType
from src.services.payment_service import calculate_order_total, process_payment

def test_calculate_order_total_100_percent_discount():
    """
    Reproduces the bug where a 100% discount results in a negative total.
    Expected: Total should be 0.00.
    Actual: Buggy code produces a negative value (e.g., -3.50).
    """
    # Setup minimal test data
    items = [
        OrderItem(product_id=1, price=43.75, quantity=1)
    ]
    # 100% discount code
    discount = Discount(code="PROMO100", type=DiscountType.PERCENTAGE, value=100)
    
    total = calculate_order_total(items, discount)
    
    # This assertion is expected to FAIL because the bug produces a negative total
    assert total == 0.00, f"Expected total to be 0.00 for 100% discount, but got {total}"

def test_process_payment_raises_value_error_on_negative_total():
    """
    Verifies that the payment processor correctly raises a ValueError 
    when passed the negative total produced by the bug.
    """
    negative_total = -3.50
    
    with pytest.raises(ValueError, match="Payment amount must be positive"):
        process_payment(negative_total)