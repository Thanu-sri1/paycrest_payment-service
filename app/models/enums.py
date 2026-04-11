from enum import Enum

class Roles(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    MANAGER = "manager"
    VERIFICATION = "verification"

class LoanCollection(str, Enum):
    PERSONAL = "personal_loans"
    VEHICLE = "vehicle_loans"
    EDUCATION = "education_loans"
    HOME = "home_loans"

class DocumentType(str, Enum):
    PAN_CARD = "pan_card"
    AADHAR_CARD = "aadhar_card"
    PAY_SLIP = "pay_slip"
    VEHICLE_PRICE_DOC = "vehicle_price_doc"
    HOME_PROPERTY_DOC = "home_property_doc"
    FEES_STRUCTURE = "fees_structure"
    BONAFIDE_CERTIFICATE = "bonafide_certificate"
    COLLATERAL_DOC = "collateral_doc"

class LoanStatus:
    APPLIED = "applied"
    ASSIGNED_TO_VERIFICATION = "assigned_to_verification"
    VERIFICATION_DONE = "verification_done"
    MANAGER_APPROVED = "manager_approved"
    PENDING_ADMIN_APPROVAL = "pending_admin_approval"
    ADMIN_APPROVED = "admin_approved"
    REJECTED = "rejected"
    SANCTION_SENT = "sanction_sent"
    SIGNED_RECEIVED = "signed_received"
    READY_FOR_DISBURSEMENT = "ready_for_disbursement"
    ACTIVE = "active"
    FORECLOSED = "foreclosed"
    COMPLETED = "completed"
    DISBURSED = "disbursed"

class VechicleType(str, Enum):
    TWO_WHEELER = "two_wheeler"
    FOUR_WHEELER = "four_wheeler"


class PropertyType(str, Enum):
    APARTMENT = "apartment"
    INDEPENDENT_HOUSE = "independent_house"
    VILLA = "villa"
    PLOT = "plot"
    COMMERCIAL = "commercial"

class EmploymentStatus(str, Enum):
    EMPLOYED = "employed"
    SELF_EMPLOYED = "self-employed"
    UNEMPLOYED = "unemployed"
    STUDENT = "student"
    RETIRED = "retired"

class Gender(str, Enum ):
    MALE ="male"
    FEMALE ="female"

class MaritalStatus(str, Enum):
    SINGLE = "single"
    MARRIED = "married"
    DIVORCED = "divorced"
    WIDOWED = "widowed"
