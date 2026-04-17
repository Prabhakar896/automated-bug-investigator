"""
Sample FastAPI REST API — Payment Processing Service.

This application contains an intentional bug in the payment/discount
calculation logic for testing the automated bug investigation pipeline.
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.models import Discount, DiscountType, OrderItem
from src.services.payment_service import create_order_with_discount
from src.services.user_service import create_user, get_user, list_users

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Antigravity Payment Service",
    version="2.4.1",
    description="Payment processing API with order management",
)


# --- Request/Response Schemas ---

class CreateUserRequest(BaseModel):
    name: str
    email: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    is_active: bool


class OrderItemRequest(BaseModel):
    name: str
    quantity: int = Field(ge=1)
    unit_price: float = Field(gt=0)


class DiscountRequest(BaseModel):
    code: str
    discount_type: str = "percentage"  # "percentage" or "fixed"
    value: float = Field(ge=0)


class CreateOrderRequest(BaseModel):
    user_id: str
    items: list[OrderItemRequest]
    discount: Optional[DiscountRequest] = None


class OrderResponse(BaseModel):
    id: str
    user_id: str
    status: str
    subtotal: float
    tax_amount: float
    discount_amount: float
    total: float
    payment_id: Optional[str] = None
    error_message: Optional[str] = None


# --- Endpoints ---

@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "2.4.1"}


@app.post("/users", response_model=UserResponse)
def api_create_user(req: CreateUserRequest):
    try:
        user = create_user(req.name, req.email)
        return UserResponse(
            id=user.id, name=user.name, email=user.email, is_active=user.is_active
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/users", response_model=list[UserResponse])
def api_list_users():
    return [
        UserResponse(id=u.id, name=u.name, email=u.email, is_active=u.is_active)
        for u in list_users()
    ]


@app.post("/orders", response_model=OrderResponse)
def api_create_order(req: CreateOrderRequest):
    """Create an order with optional discount — this triggers the bug."""
    items = [
        OrderItem(name=i.name, quantity=i.quantity, unit_price=i.unit_price)
        for i in req.items
    ]

    discount = None
    if req.discount:
        dtype = (
            DiscountType.PERCENTAGE
            if req.discount.discount_type == "percentage"
            else DiscountType.FIXED
        )
        discount = Discount(
            code=req.discount.code,
            discount_type=dtype,
            value=req.discount.value,
        )

    try:
        order = create_order_with_discount(
            user_id=req.user_id, items=items, discount=discount
        )
        return OrderResponse(
            id=order.id,
            user_id=order.user_id,
            status=order.status.value,
            subtotal=order.subtotal,
            tax_amount=order.tax_amount,
            discount_amount=order.discount_amount,
            total=order.total,
            payment_id=order.payment_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Payment processing failed: {str(e)}",
        )
