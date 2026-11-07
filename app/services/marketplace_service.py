from app.repositories.marketplace_repository import MarketplaceRepository
from app.schemas.marketplace import ProductCreate, ProductPublic, ProductUpdate


def create_product(repository: MarketplaceRepository, farmer_id: str, payload: ProductCreate) -> ProductPublic:
    return ProductPublic.model_validate(repository.create(farmer_id, payload.model_dump()))


def update_product(
    repository: MarketplaceRepository,
    product_id: str,
    farmer_id: str,
    payload: ProductUpdate,
) -> ProductPublic | None:
    document = repository.update(product_id, farmer_id, payload.model_dump(exclude_unset=True))
    return ProductPublic.model_validate(document) if document else None
