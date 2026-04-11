from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class TransactionType(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"

class TransactionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"

class WalletTransaction(BaseModel):
    transaction_id: str
    customer_id: str | int
    type: TransactionType  # credit or debit
    amount: float
    description: str
    status: TransactionStatus = TransactionStatus.SUCCESS
    previous_balance: float
    new_balance: float
    initiated_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True

class Wallet(BaseModel):
    customer_id: str | int
    balance: float = 0.0
    total_credited: float = 0.0
    total_debited: float = 0.0
    transaction_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        use_enum_values = True

class MPINSetupRequest(BaseModel):
    mpin: str = Field(..., min_length=4, max_length=4, pattern="^[0-9]{4}$")
    confirm_mpin: str = Field(..., min_length=4, max_length=4)

class MPINVerifyRequest(BaseModel):
    mpin: str = Field(..., min_length=4, max_length=4, pattern="^[0-9]{4}$")

class MPINResetRequest(BaseModel):
    old_mpin: str = Field(..., min_length=4, max_length=4, pattern="^[0-9]{4}$")
    new_mpin: str = Field(..., min_length=4, max_length=4, pattern="^[0-9]{4}$")
    confirm_mpin: str = Field(..., min_length=4, max_length=4, pattern="^[0-9]{4}$")

class MPINResetWithPasswordRequest(BaseModel):
    password: str = Field(..., min_length=1)
    new_mpin: str = Field(..., min_length=4, max_length=4, pattern="^[0-9]{4}$")
    confirm_mpin: str = Field(..., min_length=4, max_length=4, pattern="^[0-9]{4}$")

class AddMoneyRequest(BaseModel):
    amount: float = Field(..., gt=0)
    mpin: str = Field(..., min_length=4, max_length=4, pattern="^[0-9]{4}$")
    description: str = "Manual top-up"

class TransactionHistoryResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int

class WalletBalanceResponse(BaseModel):
    balance: float
    total_credited: float
    total_debited: float
    transaction_count: int
    last_transaction_at: Optional[str] = None
