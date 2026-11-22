from fastapi import APIRouter, HTTPException, Query

from app.schemas.advisory import PestKnowledgeList, PestKnowledgePublic
from app.services.pest_knowledge_service import get_pest_knowledge, list_pest_knowledge

router = APIRouter(prefix="/pest-knowledge", tags=["Pest Knowledge"])


@router.get("", response_model=PestKnowledgeList, summary="List source-linked, non-chemical pest education")
def list_pests(crop_name: str | None = Query(None, min_length=2, max_length=80)):
    items = list_pest_knowledge(crop_name)
    return PestKnowledgeList(items=items, total=len(items))


@router.get("/{slug}", response_model=PestKnowledgePublic, summary="Get source-linked information about one pest")
def pest_detail(slug: str):
    result = get_pest_knowledge(slug)
    if result is None:
        raise HTTPException(status_code=404, detail="No reviewed pest information is available for this entry")
    return result
