"""Source-linked educational pest information; no pest classifier is implied."""

CHECKED_AT = "2026-11-22"

_PESTS = [
    {
        "slug": "fall-armyworm",
        "common_name": "Fall armyworm",
        "scientific_name": "Spodoptera frugiperda",
        "crops_affected": ["Maize"],
        "identification": ["Look for fresh leaf feeding and damage around the maize whorl; other causes can look similar."],
        "damage_signs": ["Leaf feeding and frass around the whorl may be observed. Confirm with careful field scouting; this system does not identify pests from images."],
        "prevention_and_nonchemical_management": [
            "Walk and inspect the crop systematically, including the whorl, and keep notes on where and when damage is seen.",
            "KALRO describes integrated management options including cultural practices and conserving natural enemies; ask local extension staff which options fit the crop stage and location.",
            "Do not treat a trap catch or a single damaged leaf as proof that a pesticide is needed.",
        ],
        "sources": [
            {"organization": "KALRO", "title": "Maize TIMPs Volume 2: Integrated Management of Fall Army Worm", "url": "https://www.kalro.org/navcdp/docs/MAIZE%20TIMPS%20Volume%202%20for%20upload.pdf"},
            {"organization": "FAO", "title": "Fall Armyworm Scouting Guidance Note 2", "url": "https://www.fao.org/fileadmin/templates/fcc/Fall_Armyworm/web_FINAL-guidance-note-2.pdf"},
        ],
        "chemical_guidance_available": False,
        "review_state": "SOURCE_CHECKED",
    },
    {
        "slug": "tomato-whitefly",
        "common_name": "Whitefly",
        "scientific_name": "Bemisia tabaci (described in the KALRO tomato reference)",
        "crops_affected": ["Tomato"],
        "identification": ["KALRO illustrates whiteflies on tomato leaves; compare field observations with the reference or ask an extension officer."],
        "damage_signs": ["KALRO describes sap feeding, leaf yellowing, honeydew-associated sooty mould under heavy infestation, and possible leaf fall."],
        "prevention_and_nonchemical_management": [
            "Inspect leaf undersides and record symptoms and affected areas; several causes can produce similar symptoms.",
            "Use integrated crop protection advice from KALRO or county extension; this system does not infer a chemical product or rate.",
        ],
        "sources": [
            {"organization": "KALRO", "title": "Tomato TIMPs: Integrated Control Practices for Whiteflies", "url": "https://www.kalro.org/navcdp/docs/tot_timps/TOMATO%20TIMPS.pdf"},
        ],
        "chemical_guidance_available": False,
        "review_state": "SOURCE_CHECKED",
    },
]


def list_pest_knowledge(crop_name: str | None = None) -> list[dict]:
    if crop_name is None:
        return [dict(item, source_checked_at=CHECKED_AT) for item in _PESTS]
    normalized = crop_name.strip().casefold()
    normalized = {"tomatoes": "tomato", "corn": "maize", "corn (maize)": "maize"}.get(normalized, normalized)
    return [dict(item, source_checked_at=CHECKED_AT) for item in _PESTS if any(crop.casefold() == normalized for crop in item["crops_affected"])]


def get_pest_knowledge(slug: str) -> dict | None:
    for item in _PESTS:
        if item["slug"] == slug:
            return dict(item, source_checked_at=CHECKED_AT)
    return None
