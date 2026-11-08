from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.dependencies import get_current_user, get_market_price_repository, require_roles
from app.models.user import UserRole
from app.repositories.market_price_repository import MarketPriceRepository
from app.schemas.market_price import MarketPriceComparison, MarketPriceCreate, MarketPriceListResponse, MarketPricePublic, MarketPriceUpdate
from app.schemas.user import UserPublic
from app.services.market_price_service import add_market_price, revise_market_price

router = APIRouter(prefix="/market-prices", tags=["Market Prices"])
PriceId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
CanManage = Depends(require_roles(UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER))
CanRead = Depends(require_roles(UserRole.FARMER, UserRole.BUYER, UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER))


@router.post("", response_model=MarketPricePublic, status_code=status.HTTP_201_CREATED, summary="Record an observed market price")
def post_market_price(payload: MarketPriceCreate, user: UserPublic = CanManage, repo: MarketPriceRepository = Depends(get_market_price_repository)):
    return MarketPricePublic.model_validate(add_market_price(repo, user.id, payload.model_dump()))


@router.get("", response_model=MarketPriceListResponse, summary="List price observations with filters")
def list_market_prices(crop_name: str | None = Query(None, min_length=2, max_length=100), county: str | None = Query(None, min_length=2, max_length=80), market_location: str | None = Query(None, min_length=2, max_length=120), start_date: date | None = None, end_date: date | None = None, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), _: UserPublic = CanRead, repo: MarketPriceRepository = Depends(get_market_price_repository)):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    items, total = repo.list_prices(crop_name=crop_name, county=county, market_location=market_location, start_date=start_date, end_date=end_date, skip=offset, limit=limit)
    return MarketPriceListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/compare", response_model=MarketPriceComparison, summary="Compare the latest recorded price at each market")
def compare_market_prices(crop_name: str = Query(min_length=2, max_length=100), county: str | None = Query(None, min_length=2, max_length=80), _: UserPublic = CanRead, repo: MarketPriceRepository = Depends(get_market_price_repository)):
    items = repo.compare(crop_name=crop_name, county=county)
    return MarketPriceComparison(crop_name=crop_name, county=county, items=items)


@router.get("/history", response_model=MarketPriceListResponse, summary="Retrieve historical observations for a crop")
def market_price_history(crop_name: str = Query(min_length=2, max_length=100), county: str | None = Query(None, min_length=2, max_length=80), start_date: date | None = None, end_date: date | None = None, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), _: UserPublic = CanRead, repo: MarketPriceRepository = Depends(get_market_price_repository)):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    items, total = repo.list_prices(crop_name=crop_name, county=county, market_location=None, start_date=start_date, end_date=end_date, skip=offset, limit=limit)
    return MarketPriceListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/{price_id}/revision", response_model=MarketPricePublic, status_code=status.HTTP_201_CREATED, summary="Add a corrected observation without erasing history")
def revise_price(price_id: PriceId, payload: MarketPriceUpdate, user: UserPublic = CanManage, repo: MarketPriceRepository = Depends(get_market_price_repository)):
    revised = revise_market_price(repo, price_id, user.id, payload.model_dump())
    if revised is None:
        raise HTTPException(status_code=404, detail="Market price record not found")
    return MarketPricePublic.model_validate(revised)
