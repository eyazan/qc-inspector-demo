from fastapi import APIRouter, Depends

from app.api.deps import get_spec_service
from app.schemas import SpecQueryRequest, SpecQueryResponse
from app.services.spec_service import SpecService

router = APIRouter(prefix="/api", tags=["spec"])


@router.post("/query", response_model=SpecQueryResponse)
def query_spec(
    request: SpecQueryRequest,
    service: SpecService = Depends(get_spec_service),
) -> SpecQueryResponse:
    return service.query(request)
