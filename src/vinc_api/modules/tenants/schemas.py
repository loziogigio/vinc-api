try:
    from pydantic import BaseModel
except Exception:  # pragma: no cover
    class BaseModel:  # type: ignore
        pass


class TenantInfo(BaseModel):
    tenant_id: str | None

