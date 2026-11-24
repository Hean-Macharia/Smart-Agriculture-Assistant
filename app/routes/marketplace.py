from io import BytesIO
from pathlib import Path
from secrets import token_hex
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.core.config import BACKEND_ROOT, settings
from app.core.dependencies import get_current_user, get_marketplace_repository, require_roles
from app.models.user import UserRole
from app.repositories.marketplace_repository import MarketplaceRepository
from app.schemas.marketplace import ProductCreate, ProductListResponse, ProductPublic, ProductUpdate
from app.schemas.user import UserPublic
from app.services.marketplace_service import create_product, update_product

router = APIRouter(prefix="/marketplace/products", tags=["Marketplace"])
ProductId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
MAX_PRODUCT_IMAGE_PIXELS = 20_000_000


@router.post("/images", status_code=status.HTTP_201_CREATED, summary="Upload a validated marketplace image (local development storage)")
async def upload_product_image(
    image: Annotated[UploadFile, File(description="JPEG, PNG or WebP image; max 5 MiB by default")],
    _: UserPublic = Depends(require_roles(UserRole.FARMER)),
):
    if settings.app_env.lower() not in {"development", "dev", "test", "testing", "local"}:
        raise HTTPException(status_code=503, detail="Production image storage is not configured")
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        await image.close()
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP image")
    try:
        raw = await image.read(settings.product_image_max_bytes + 1)
    finally:
        await image.close()
    if len(raw) > settings.product_image_max_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the configured upload limit")
    if not raw:
        raise HTTPException(status_code=422, detail="Image file is empty")
    try:
        with Image.open(BytesIO(raw)) as image_source:
            if image_source.width * image_source.height > MAX_PRODUCT_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="Image dimensions exceed the supported limit")
            if image_source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP image")
            image_source.load()
            image_source.thumbnail((1600, 1600))
            normalized = image_source.convert("RGB")
            output = BytesIO()
            normalized.save(output, format="WEBP", quality=82, method=4)
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail="Image file is invalid or could not be decoded") from None
    directory = BACKEND_ROOT / "uploads" / "product_images"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{token_hex(16)}.webp"
    (directory / filename).write_bytes(output.getvalue())
    return {"url": f"/media/products/{filename}", "content_type": "image/webp", "width": normalized.width, "height": normalized.height}


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
