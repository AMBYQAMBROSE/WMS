# 导入全部模型，确保任何一处 import app.models.xxx 时外键引用的表都已注册到 Base.metadata
from app.models import (  # noqa: F401
    business_partner,
    document,
    item,
    location,
    stock,
    tenant,
    user,
)
