"""
Canonical trade list + keyword map.

Each trade has:
  - "label": display name in the UI
  - "keywords": substrings (lowercase) used to match free-text fields
                (permit work descriptions, business names, etc.)
  - "permit_types": values seen in the Chicago permit dataset that map here
"""

TRADES: dict[str, dict] = {
    "General Contractor": {
        "keywords": ["general contractor", "gc ", "construction"],
        "permit_types": ["PERMIT - NEW CONSTRUCTION", "PERMIT - RENOVATION/ALTERATION"],
    },
    "Framing / Carpentry": {
        "keywords": ["framing", "carpenter", "carpentry", "rough carpentry", "finish carpentry"],
        "permit_types": [],
    },
    "Millwork": {
        "keywords": ["millwork", "casework", "cabinet", "cabinetry", "architectural woodwork"],
        "permit_types": [],
    },
    "Doors, Frames & Hardware": {
        "keywords": ["door", "frame", "hardware", "dfh", "hollow metal"],
        "permit_types": [],
    },
    "Glazing / Glass": {
        "keywords": ["glazing", "glass", "curtain wall", "storefront", "window install"],
        "permit_types": [],
    },
    "Electrical": {
        "keywords": ["electric", "electrician", "low voltage", "lighting"],
        "permit_types": ["PERMIT - ELECTRIC WIRING"],
    },
    "Plumbing": {
        "keywords": ["plumb", "plumber", "piping", "water service"],
        "permit_types": ["PERMIT - NEW CONSTRUCTION", "PERMIT - RENOVATION/ALTERATION"],
    },
    "HVAC / Mechanical": {
        "keywords": ["hvac", "mechanical", "heating", "cooling", "air conditioning", "refrigeration", "ductwork"],
        "permit_types": [],
    },
    "Fire Protection / Sprinkler": {
        "keywords": ["sprinkler", "fire protection", "fire suppression", "fire alarm"],
        "permit_types": [],
    },
    "Roofing": {
        "keywords": ["roof", "roofing", "shingle", "membrane"],
        "permit_types": [],
    },
    "Siding / Exterior": {
        "keywords": ["siding", "cladding", "exterior", "eifs", "stucco"],
        "permit_types": [],
    },
    "Concrete": {
        "keywords": ["concrete", "cement", "foundation", "footing", "slab"],
        "permit_types": [],
    },
    "Masonry": {
        "keywords": ["mason", "masonry", "brick", "block", "stone", "tuckpointing"],
        "permit_types": [],
    },
    "Steel / Structural Steel": {
        "keywords": ["steel", "structural steel", "miscellaneous metals", "ironwork"],
        "permit_types": [],
    },
    "Drywall / Plaster": {
        "keywords": ["drywall", "plaster", "gypsum", "gyp board", "taping"],
        "permit_types": [],
    },
    "Painting": {
        "keywords": ["paint", "painter", "painting", "coatings"],
        "permit_types": [],
    },
    "Flooring": {
        "keywords": ["floor", "flooring", "tile", "carpet", "hardwood", "vct", "lvt"],
        "permit_types": [],
    },
    "Acoustical Ceilings": {
        "keywords": ["acoustical", "act ceiling", "ceiling tile", "suspended ceiling"],
        "permit_types": [],
    },
    "Insulation": {
        "keywords": ["insulation", "spray foam", "blown-in"],
        "permit_types": [],
    },
    "Waterproofing": {
        "keywords": ["waterproof", "waterproofing", "damp proofing"],
        "permit_types": [],
    },
    "Excavation / Earthwork": {
        "keywords": ["excavation", "earthwork", "grading", "site work", "site prep"],
        "permit_types": ["PERMIT - WRECKING/DEMOLITION"],
    },
    "Demolition": {
        "keywords": ["demo", "demolition", "wrecking"],
        "permit_types": ["PERMIT - WRECKING/DEMOLITION"],
    },
    "Landscaping": {
        "keywords": ["landscape", "landscaping", "irrigation"],
        "permit_types": [],
    },
    "Paving / Asphalt": {
        "keywords": ["paving", "asphalt", "blacktop"],
        "permit_types": [],
    },
    "Elevators": {
        "keywords": ["elevator", "lift", "escalator"],
        "permit_types": ["PERMIT - ELEVATOR EQUIPMENT"],
    },
    "Signage": {
        "keywords": ["sign", "signage"],
        "permit_types": ["PERMIT - SIGNS"],
    },
    "Environmental / Abatement": {
        "keywords": ["asbestos", "abatement", "lead", "environmental", "remediation"],
        "permit_types": [],
    },
}


def all_trade_labels() -> list[str]:
    return list(TRADES.keys())


def keywords_for(trade_label: str) -> list[str]:
    return TRADES.get(trade_label, {}).get("keywords", [])


def classify(text) -> list[str]:
    """Return list of matching trade labels for a free-text string."""
    if not isinstance(text, str) or not text:
        return []
    t = text.lower()
    hits = []
    for label, meta in TRADES.items():
        for kw in meta["keywords"]:
            if kw in t:
                hits.append(label)
                break
    return hits
