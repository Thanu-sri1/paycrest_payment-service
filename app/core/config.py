from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional


class Settings(BaseSettings):
    SERVICE_NAME: Optional[str] = "payment-service"
    API_PREFIX: str = "/api"
    PORT: Optional[int] = 3005
    ENVIRONMENT: Optional[str] = "development"

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "pycrest"

    JWT_SECRET: str = "CHANGE_ME"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24
    ACCESS_TOKEN_EXPIRE_MINUTES: Optional[int] = 60

    IDEMPOTENCY_ENABLED: bool = True
    IDEMPOTENCY_TTL_HOURS: int = 24

    DEFAULT_IFSC: str = "PCIN01001"
    INTERNAL_SERVICE_TOKEN: str = "CHANGE_ME"

    CASHFREE_ENV: str = "sandbox"
    CASHFREE_CLIENT_ID: Optional[str] = None
    CASHFREE_CLIENT_SECRET: Optional[str] = None
    CASHFREE_API_VERSION: str = "2023-08-01"
    CASHFREE_RETURN_URL: str = "http://localhost:5173/customer/dashboard"
    CASHFREE_RETURN_URL_WALLET: str = "http://localhost:5173/customer/wallet"
    CASHFREE_RETURN_URL_EMI: str = "http://localhost:5173/customer/emi"
    CASHFREE_WEBHOOK_URL: str = "http://localhost:8010/api/payments/cashfree/webhook"
    CASHFREE_ORDER_PREFIX: str = "pc_emi_"
    CASHFREE_HTTP_TIMEOUT_SECONDS: int = 20

    WALLET_SERVICE_URL: Optional[str] = None
    AUTH_SERVICE_URL: Optional[str] = None
    LOAN_SERVICE_URL: Optional[str] = None
    EMI_SERVICE_URL: Optional[str] = None
    PAYMENT_SERVICE_URL: Optional[str] = None
    VERIFICATION_SERVICE_URL: Optional[str] = None
    ADMIN_SERVICE_URL: Optional[str] = None
    MANAGER_SERVICE_URL: Optional[str] = None

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="allow"
    )


settings = Settings()