from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.permission_catalog import catalog_payload
from app.core.permissions import get_current_user

router = APIRouter(prefix='/api/permissions', tags=['permissions'])


@router.get('/catalog')
async def permission_catalog(user=Depends(get_current_user)):
    return JSONResponse(catalog_payload())
