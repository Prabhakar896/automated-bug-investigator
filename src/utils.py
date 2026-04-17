"""
Utility functions for the sample application.
"""

import logging
from datetime import datetime

logger = logging.getLogger("app")


def format_currency(amount: float) -> str:
    """Format a float as a USD currency string."""
    return f"${amount:,.2f}"


def validate_email(email: str) -> bool:
    """Basic email format validation."""
    return "@" in email and "." in email.split("@")[-1]


def generate_payment_reference() -> str:
    """Generate a unique payment reference number."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"PAY-{timestamp}"


def calculate_tax(subtotal: float, tax_rate: float = 0.08) -> float:
    """Calculate tax amount for a given subtotal.
    
    Args:
        subtotal: The pre-tax amount
        tax_rate: Tax rate as a decimal (default 8%)
    
    Returns:
        The tax amount rounded to 2 decimal places
    """
    return round(subtotal * tax_rate, 2)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max bounds."""
    return max(min_val, min(value, max_val))
