"""Source-backed, non-chemical education for the classifier's supported labels.

This catalogue deliberately contains no pesticide/product recommendations. It
provides general practices summarized from Kenyan government and KALRO sources;
it is not a diagnosis and is not a substitute for local extension review.
"""

from copy import deepcopy


_KALRO_MAIZE = {
    "organization": "Kenya Agricultural and Livestock Research Organization (KALRO)",
    "title": "The Kenya Cereals Enhancement Programme – Climate: Maize diseases",
    "url": "https://kalroerepository.kalro.org/bitstreams/c734f0b2-bae2-4941-b804-bc466914e4ba/download",
    "reference": "Sections 3.4.2–3.4.4, PDF pages 11–12",
}
_KALRO_COMMON_RUST = {
    "organization": "Kenya Agricultural and Livestock Research Organization (KALRO)",
    "title": "The Kenya Cereals Enhancement: maize production guide",
    "url": "https://kalroerepository.kalro.org/server/api/core/bitstreams/9757742b-5d9c-4e40-856f-6476373a3d49/content",
    "reference": "Section 3.4.5, PDF page 25",
}
_KENYA_TOMATO = {
    "organization": "Agriculture and Food Authority (AFA), Horticultural Crops Directorate",
    "title": "Tomato Growers Manual",
    "url": "https://afa.go.ke/resources/files/bb0054ff-ee35-462e-9611-464271662830_tomato-growers-manual.pdf",
    "reference": "Tomato disease tables, PDF pages 6–7",
}
_MINISTRY_IPM = {
    "organization": "Kenya Ministry of Agriculture and Livestock Development",
    "title": "NAVCDP Integrated Pest Management Plan",
    "url": "https://kilimo.go.ke/wp-content/uploads/2024/12/NAVCDP-IPMP-March-2023.pdf",
    "reference": "Tomato and potato disease management tables",
}
_KENYA_POTATO = {
    "organization": "National Potato Council of Kenya and partners",
    "title": "Kenya Potato Guide: Potato Production in Kenya",
    "url": "https://www.apni.net/wp-content/uploads/2021/08/Kenya-Potato-Guide-0821-.pdf",
    "reference": "Chapter 4, pages 81–84",
}


def _entry(label, crop, display, scientific, summary, symptoms, guidance, sources):
    return {
        "model_label": label,
        "crop_name": crop,
        "display_name": display,
        "scientific_name": scientific,
        "summary": summary,
        "symptoms": symptoms,
        "general_guidance": guidance,
        "sources": sources,
        "source_checked_at": "2026-11-22",
        "review_state": "SOURCE_CHECKED",
        "guidance_status": "SOURCE_BACKED_GENERAL_GUIDANCE",
        "chemical_guidance_available": False,
        "disclaimer": (
            "This is general educational guidance associated with a model class. "
            "Image screening may be wrong or miss other causes. Ask a county "
            "agricultural extension officer to confirm serious or uncertain cases."
        ),
    }


_KNOWLEDGE = (
    _entry(
        "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot", "Maize", "Maize – Gray Leaf Spot",
        "Cercospora zeae-maydis / Cercospora zeina",
        "A maize leaf disease associated with lesions that develop along leaf veins and may merge as they mature.",
        ["Brown, elongated lesions following leaf veins; older lesions may merge and appear grey, often starting on lower leaves."],
        ["Use locally suitable tolerant varieties and clean seed.", "Manage infected crop residue and volunteer maize after harvest.", "Rotate with non-host crops; confirm locally appropriate rotation length with an extension officer."],
        [_KALRO_MAIZE],
    ),
    _entry(
        "Corn_(maize)___Common_rust_", "Maize", "Maize – Common Rust",
        "Puccinia sorghi",
        "A maize rust class associated with raised rust-coloured pustules on leaf surfaces.",
        ["Raised red-brown pustules may occur on both leaf surfaces, often around the middle or upper canopy."],
        ["Use locally suitable tolerant varieties and seed from a reliable source.", "Manage crop residues and rotate maize with non-host crops where suitable.", "Seek local advice if pustules spread quickly or foliage is being lost."],
        [_KALRO_COMMON_RUST],
    ),
    _entry(
        "Corn_(maize)___Northern_Leaf_Blight", "Maize", "Maize – Northern Leaf Blight",
        "Exserohilum turcicum",
        "A maize leaf blight class that can produce long, cigar-shaped lesions, especially on lower leaves.",
        ["Lesions may begin as small chlorotic areas and develop into elongated, cigar-shaped dead areas on leaves."],
        ["Use locally suitable resistant varieties and clean seed.", "Remove or manage infected maize residue and volunteer plants after harvest.", "Rotate with non-host crops and seek extension advice if disease is progressing rapidly."],
        [_KALRO_MAIZE],
    ),
    _entry(
        "Corn_(maize)___healthy", "Maize", "Maize – No Target Disease Class Detected",
        None,
        "The model did not select one of its supported maize disease classes as the top class. This does not prove the plant is healthy.",
        [],
        ["Continue regular field scouting.", "If visible symptoms persist, submit a clear image and request confirmation from an agricultural extension officer."],
        [_KALRO_MAIZE],
    ),
    _entry(
        "Potato___Early_blight", "Potato", "Potato – Early Blight",
        "Alternaria solani",
        "An early blight class often associated with older foliage and dark lesions.",
        ["Dark brown spots may first appear on older or lower leaves and enlarge; affected leaves may yellow and die."],
        ["Use clean seed and maintain field sanitation.", "Remove volunteer potato plants and manage infected crop debris safely.", "Rotate away from potato where practical and request local confirmation if symptoms continue."],
        [_KENYA_POTATO, _MINISTRY_IPM],
    ),
    _entry(
        "Potato___Late_blight", "Potato", "Potato – Late Blight",
        "Phytophthora infestans",
        "A potentially fast-spreading potato disease associated with cool, humid conditions; seek prompt field confirmation when suspected.",
        ["Water-soaked foliage lesions may turn brown when dry; white growth may appear at lesion edges on leaf undersides. Stems and tubers may also be affected."],
        ["Use certified, disease-free seed potatoes and locally suitable varieties.", "Scout frequently during cool, wet periods and seek prompt extension advice for suspected outbreaks.", "Manage infected plants and residues according to local extension guidance; do not compost diseased material unless advised."],
        [_KENYA_POTATO, _MINISTRY_IPM],
    ),
    _entry(
        "Potato___healthy", "Potato", "Potato – No Target Disease Class Detected",
        None,
        "The model did not select one of its supported potato disease classes as the top class. This does not prove the plant is healthy.",
        [],
        ["Continue routine crop scouting, especially during wet weather.", "Request extension review if symptoms remain visible or worsen."],
        [_KENYA_POTATO],
    ),
    _entry(
        "Tomato___Bacterial_spot", "Tomato", "Tomato – Bacterial Spot",
        "Xanthomonas spp.",
        "A bacterial disease class associated with leaf and fruit spotting; it is more likely to develop in wet conditions.",
        ["Small dark or water-soaked spots may appear on foliage and fruit; lesions can lead to leaf loss and fruit damage."],
        ["Use certified disease-free seed and healthy transplants.", "Avoid overhead irrigation where possible and reduce prolonged leaf wetness.", "Remove and dispose of diseased plant material safely, clean tools, and rotate away from tomato and pepper where practical."],
        [_MINISTRY_IPM],
    ),
    _entry(
        "Tomato___Early_blight", "Tomato", "Tomato – Early Blight",
        "Alternaria solani",
        "A tomato leaf disease class commonly associated with dark, target-like lesions on older foliage.",
        ["Brown or black lesions may show concentric rings and yellowing, often beginning on lower or older leaves."],
        ["Use clean seed and healthy transplants.", "Maintain field sanitation and rotate with non-solanaceous crops where practical.", "Use spacing and irrigation practices that help foliage dry; request local advice if disease is spreading."],
        [_KENYA_TOMATO],
    ),
    _entry(
        "Tomato___Late_blight", "Tomato", "Tomato – Late Blight",
        "Phytophthora infestans",
        "A tomato blight class that may spread quickly in cool, humid or wet conditions.",
        ["Water-soaked dark lesions may develop on leaves and stems; fruit may develop water-soaked or grey-brown spots."],
        ["Scout closely during cool, wet periods and seek prompt extension confirmation.", "Remove volunteer host plants and improve air movement through suitable pruning and staking.", "Avoid prolonged leaf wetness and follow local extension guidance for safe disposal of infected plants."],
        [_KENYA_TOMATO, _MINISTRY_IPM],
    ),
    _entry(
        "Tomato___healthy", "Tomato", "Tomato – No Target Disease Class Detected",
        None,
        "The model did not select one of its supported tomato disease classes as the top class. This does not prove the plant is healthy.",
        [],
        ["Continue regular crop scouting and use clean planting material.", "If symptoms persist, request confirmation from an agricultural extension officer."],
        [_KENYA_TOMATO],
    ),
)


def list_disease_knowledge(crop_name: str | None = None) -> list[dict]:
    """Return copies of the supported class records, optionally crop-filtered."""
    crop = crop_name.strip().casefold() if crop_name else None
    return [
        deepcopy(entry)
        for entry in _KNOWLEDGE
        if crop is None or entry["crop_name"].casefold() == crop
    ]


def get_disease_knowledge(model_label: str) -> dict | None:
    """Look up a knowledge record by its exact model output label."""
    for entry in _KNOWLEDGE:
        if entry["model_label"] == model_label:
            return deepcopy(entry)
    return None
