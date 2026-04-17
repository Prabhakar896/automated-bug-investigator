"""
Payment service — handles order pricing and payment processing.

*** THIS MODULE CONTAINS AN INTENTIONAL BUG ***

BUG: The calculate_order_total() function applies the discount percentage
to the subtotal AFTER adding tax, instead of BEFORE. Additionally, it does
NOT clamp the final total to zero, which means large discounts (e.g., 100%)
applied to the post-tax amount result in NEGATIVE totals.

Example:
  subtotal = $50.00, tax_rate = 8%, discount = 100%
  
  CORRECT: discount on subtotal → $50.00 - $50.00 = $0.00, tax on $0.00 = $0.00, total = $0.00
  BUGGY:   subtotal + tax = $54.00, discount 100% of $54.00 = $54.00,
           but discount is calculated as: subtotal * (discount/100) = $50.00
           total = subtotal + tax - discount = $50 + $4.00 - $50.00 = $4.00  ... 
           
  Actually the real bug is more subtle — see calculate_order_total below.
"""

import logging
from typing import Optional

from src.models import (
    Discount,
    DiscountType,
    Order,
    OrderItem,
    OrderStatus,
    PaymentResult,
)
from src.utils import calculate_tax, generate_payment_reference

logger = logging.getLogger("app.payment_service")

# Default tax rate (8%)
DEFAULT_TAX_RATE = 0.08


def calculate_order_total(
    items: list[OrderItem],
    discount: Optional[Discount] = None,
    tax_rate: float = DEFAULT_TAX_RATE,
) -> dict:
    """
    Calculate the total for an order including tax and discount.

    Returns a dict with subtotal, tax_amount, discount_amount, and total.

    BUG: Discount is applied AFTER tax is added to subtotal, and the result
    is not clamped to >= 0. For a 100% percentage discount:
      - subtotal = sum of items
      - tax = subtotal * tax_rate
      - gross = subtotal + tax
      - discount_amount = gross * (percentage / 100)   ← WRONG: should be subtotal only
      - total = gross - discount_amount                 ← can go NEGATIVE
    
    The correct behavior would be:
      - discount_amount = subtotal * (percentage / 100)
      - taxable = subtotal - discount_amount
      - tax = taxable * tax_rate
      - total = max(0, taxable + tax)
    """
    subtotal = sum(item.subtotal for item in items)
    tax_amount = calculate_tax(subtotal, tax_rate)

    # --- BUG STARTS HERE ---
    # Discount is applied to (subtotal + tax) instead of just subtotal
    gross = subtotal + tax_amount
    
    discount_amount = 0.0
    if discount is not None:
        if discount.discount_type == DiscountType.PERCENTAGE:
            # BUG: applying percentage to gross (includes tax) instead of subtotal
            discount_amount = round(gross * (discount.value / 100), 2)
        elif discount.discount_type == DiscountType.FIXED:
            discount_amount = discount.value

    # BUG: no clamping — total can be negative
    total = round(gross - discount_amount, 2)
    # --- BUG ENDS HERE ---

    return {
        "subtotal": round(subtotal, 2),
        "tax_amount": round(tax_amount, 2),
        "discount_amount": round(discount_amount, 2),
        "total": total,  # Can be negative!
    }


def process_payment(order: Order) -> PaymentResult:
    """
    Process payment for an order.
    
    Raises ValueError if the payment amount is not positive.
    """
    if order.total <= 0:
        error_msg = f"Payment amount must be positive, got: ${order.total:.2f}"
        logger.error(f"Payment failed for order {order.id}: {error_msg}")
        raise ValueError(error_msg)

    # Simulate payment processing
    payment_ref = generate_payment_reference()
    logger.info(
        f"Payment processed for order {order.id}: "
        f"${order.total:.2f} (ref: {payment_ref})"
    )
    
    return PaymentResult(
        success=True,
        payment_id=payment_ref,
        amount=order.total,
    )


def create_order_with_discount(
    user_id: str,
    items: list[OrderItem],
    discount: Optional[Discount] = None,
) -> Order:
    """
    Create an order, calculate totals, and process payment.
    
    This is the main entry point that triggers the bug when a 100%
    discount is applied.
    """
    order = Order(user_id=user_id, items=items, discount=discount)
    order.status = OrderStatus.PROCESSING

    try:
        totals = calculate_order_total(items, discount)
        order.subtotal = totals["subtotal"]
        order.tax_amount = totals["tax_amount"]
        order.discount_amount = totals["discount_amount"]
        order.total = totals["total"]

        logger.info(
            f"Order {order.id} totals: subtotal=${order.subtotal:.2f}, "
            f"tax=${order.tax_amount:.2f}, discount=${order.discount_amount:.2f}, "
            f"total=${order.total:.2f}"
        )

        # This will raise ValueError if total is negative
        result = process_payment(order)
        order.payment_id = result.payment_id
        order.status = OrderStatus.COMPLETED

    except ValueError as e:
        order.status = OrderStatus.FAILED
        order.error_message = str(e)
        logger.error(f"Order {order.id} failed: {e}")
        raise

    return order
