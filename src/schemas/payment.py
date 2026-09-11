from datetime import datetime
from decimal import Decimal
from typing import Literal
import uuid
from pydantic import BaseModel, ConfigDict


PaymentStatusType = Literal["pending", "success", "failed", "refunded"]


class PaymentStatusUpdateRequest(BaseModel):
    status: PaymentStatusType
    order_id: str | None = None
    razorpay_payment_id: str | None = None
    razorpay_signature: str | None = None


class PaymentCreateRequest(BaseModel):
    event_id: uuid.UUID
    plan: str
    amount: Decimal | float | None = None
    order_id: str | None = None


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    plan: str | None = None
    amount: Decimal | float | None = None
    status: str | None = None
    order_id: str | None = None
    razorpay_payment_id: str | None = None
    created_at: datetime
    event_status: str | None = None
