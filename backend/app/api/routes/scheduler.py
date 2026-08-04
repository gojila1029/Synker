from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user

router = APIRouter()


@router.post("/trigger")
async def trigger_discovery(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"triggered": True}
