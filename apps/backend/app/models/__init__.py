# Import every model so that tables referenced by foreign keys are registered in Base.metadata wherever app.models.xxx is imported
from app.models import (  # noqa: F401
    audit,
    business_partner,
    document,
    integration,
    item,
    location,
    reason_code,
    returnable_asset,
    stock,
    tenant,
    user,
)
