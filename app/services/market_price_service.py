from datetime import date

from app.repositories.market_price_repository import MarketPriceRepository


class MarketPriceAccessError(Exception):
    pass


def add_market_price(repository: MarketPriceRepository, recorded_by: str, payload: dict) -> dict:
    return repository.create({**payload, "recorded_by": recorded_by, "supersedes_id": None})


def revise_market_price(repository: MarketPriceRepository, price_id: str, recorded_by: str, payload: dict) -> dict | None:
    changes = {**payload, "date_collected": date.fromisoformat(payload["date_collected"]) if isinstance(payload.get("date_collected"), str) else payload["date_collected"]}
    return repository.create_revision(price_id, recorded_by, changes)
