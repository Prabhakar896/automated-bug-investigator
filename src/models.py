"""
Data models for the sample payment processing application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class OrderStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class DiscountType(Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


@dataclass
class User:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    email: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True


@dataclass
class OrderItem:
    name: str
    quantity: int
    unit_price: float

    @property
    def subtotal(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class Discount:
    code: str
    discount_type: DiscountType
    value: float  # percentage (0-100) or fixed dollar amount
    description: str = ""


@dataclass
class Order:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    items: list = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    subtotal: float = 0.0
    tax_amount: float = 0.0
    discount_amount: float = 0.0
    total: float = 0.0
    discount: Optional[Discount] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    payment_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class PaymentResult:
    success: bool
    payment_id: Optional[str] = None
    amount: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
