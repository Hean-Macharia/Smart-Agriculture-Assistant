from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.core.dependencies import get_current_user, get_marketplace_repository, require_roles
from app.models.user import UserRole
from app.repositories.marketplace_repository import MarketplaceRepository
from app.schemas.marketplace import ProductCreate, ProductListResponse, ProductPublic, ProductUpdate
from app.schemas.user import UserPublic
from app.services.marketplace_service import create_product, update_product

router = APIRouter(prefix="/marketplace/products", tags=["Marketplace"])
ProductId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


@router.post("", response_model=ProductPublic, status_code=status.HTTP_201_CREATED, summary="List produce for sale")
def post_product(
    payload: ProductCreate,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: MarketplaceRepository = Depends(get_marketplace_repository),
) -> ProductPublic:
    return create_product(repository, user.id, payload)


@router.get("/mine", response_model=ProductListResponse, summary="List my product listings")
def list_my_products(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: MarketplaceRepository = Depends(get_marketplace_repository),
) -> ProductListResponse:
    items, total = repository.list_for_farmer(user.id, skip=offset, limit=limit)
    return ProductListResponse(items=[ProductPublic.model_validate(item) for item in items], total=total, limit=limit, offset=offset)


@router.get("", response_model=ProductListResponse, summary="Browse available products")
def browse_products(
    search: str | None = Query(default=None, max_length=120),
    county: str | None = Query(default=None, max_length=80),
    category: str | None = Query(default=None, max_length=80),
    min_price_kes: int | None = Query(default=None, ge=0),
    max_price_kes: int | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    repository: MarketplaceRepository = Depends(get_marketplace_repository),
) -> ProductListResponse:
    if min_price_kes is not None and max_price_kes is not None and min_price_kes > max_price_kes:
        raise HTTPException(status_code=422, detail="min_price_kes cannot exceed max_price_kes")
    items, total = repository.list_products(
        search=search,
        county=county,
        category=category,
        min_price=min_price_kes,
        max_price=max_price_kes,
        skip=offset,
        limit=limit,
    )
    return ProductListResponse(items=[ProductPublic.model_validate(item) for item in items], total=total, limit=limit, offset=offset)


@router.get("/{product_id}", response_model=ProductPublic, summary="Get product details")
def get_product(
    product_id: ProductId,
    repository: MarketplaceRepository = Depends(get_marketplace_repository),
) -> ProductPublic:
    product = repository.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductPublic.model_validate(product)


@router.patch("/{product_id}", response_model=ProductPublic, summary="Update my product listing")
def patch_product(
    product_id: ProductId,
    payload: ProductUpdate,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: MarketplaceRepository = Depends(get_marketplace_repository),
) -> ProductPublic:
    product = update_product(repository, product_id, user.id, payload)
    if product is None:
        existing = repository.get(product_id)
        if existing and existing["farmer_id"] == user.id:
            raise HTTPException(status_code=409, detail="Inventory changed concurrently; reload and retry")
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Deactivate my product listing")
def delete_product(
    product_id: ProductId,
    user: UserPublic = Depends(require_roles(UserRole.FARMER)),
    repository: MarketplaceRepository = Depends(get_marketplace_repository),
) -> Response:
    if not repository.deactivate(product_id, user.id):
        raise HTTPException(status_code=404, detail="Product not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
