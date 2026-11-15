"""Auditable bilingual concepts and query parsing, separate from source assertions.

Alias matches are retrieval/classification hints. They never supply experimental conditions.
"""

import math
import re
import unicodedata

VERSION = "research-concepts-1"

CONCEPTS = {
    "pmma": ["pmma", "acrylic", "acrylics", "acrilico", "acrilicos", "polymethyl methacrylate"],
    "polymers": ["polymer", "polymers", "polimero", "polimeros"],
    "cellulose": ["cellulose", "celulosa", "cotton", "algodon"],
    "droplet": ["droplet", "droplets", "gota", "gotas"],
    "methane": ["methane", "metano"],
    "heptane": ["heptane", "heptano"],
    "hydrogen": ["hydrogen", "hidrogeno"],
    "flame_spread": ["flame spread", "flame propagation", "fire spread", "propagacion de fuego",
                     "propagacion del fuego", "propagacion de llamas", "propagacion de la llama"],
    "flammability": ["flammability", "flammable", "inflamabilidad", "inflamable"],
    "detection": ["fire detection", "smoke detection", "deteccion de incendios", "deteccion de humo"],
    "suppression": ["fire suppression", "extinguishing", "supresion", "extincion de incendios"],
    "modeling": ["modeling", "modelling", "simulation", "simulacion", "modelo computacional"],
    "smoke": ["smoke", "soot", "aerosol", "aerosols", "humo", "hollin", "aerosoles"],
    "safety": ["fire safety", "spacecraft fire", "seguridad contra incendios", "seguridad espacial"],
    "combustion": ["combustion", "flame", "flames", "llama", "llamas"],
    "extinction": ["extinction", "extincion", "apagado"],
    "ignition": ["ignition", "ignicion", "encendido"],
    "microgravity": ["microgravity", "microgravedad", "zero gravity", "gravedad cero"],
    "ground": ["terrestrial", "normal gravity", "gravedad terrestre", "ground investigation"],
    "oxygen": ["oxygen", "oxigeno", "o2"],
    "pressure": ["pressure", "presion"],
    "flow": ["flow", "ventilation", "airflow", "flujo", "ventilacion"],
    "camera": ["camera", "cameras", "camara", "camaras", "imaging"],
    "sensor": ["sensor", "sensors", "sensores", "thermocouple", "termopar"],
    "lunar_base": ["lunar base", "base lunar", "moon base"],
    "mars_base": ["mars base", "martian base", "base marciana", "base de marte"],
    "space_station": ["space station", "estacion espacial", "iss"],
    "spacecraft": ["spacecraft", "nave espacial", "naves espaciales"],
    "pressurized_vehicle": ["pressurized vehicle", "vehiculo presurizado"],
}

CATEGORIES = {
    "Flame Propagation": ["flame_spread"],
    "Material Flammability": ["flammability"],
    "Fire Detection": ["detection"],
    "Fire Suppression": ["suppression"],
    "Combustion Modeling": ["modeling"],
    "Smoke and Aerosols": ["smoke"],
    "Spacecraft Fire Safety": ["safety"],
    "Combustion Fundamentals": ["combustion", "extinction", "ignition"],
}
FACETS = {
    "materials": ["pmma", "polymers", "cellulose"],
    "fuels": ["methane", "heptane", "hydrogen", "pmma", "cellulose"],
    "gravity": ["microgravity", "ground"],
    "variables": ["oxygen", "pressure", "flow", "extinction", "ignition", "flame_spread"],
    "instrumentation": ["camera", "sensor"],
    "security_applications": ["safety", "detection", "suppression", "smoke"],
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower().replace("₂", "2"))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def matches(text: str, alias: str) -> bool:
    return bool(re.search(r"(?<![\w-])" + re.escape(normalize(alias)) + r"(?![\w-])", normalize(text)))


def concepts(text: str) -> list[str]:
    return [key for key, aliases in CONCEPTS.items() if any(matches(text, a) for a in aliases)]


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", normalize(text)))


def concept_vector(text: str) -> list[float]:
    """Small deterministic semantic embedding in a versioned bilingual concept space."""
    found = set(concepts(text))
    v = [float(key in found) for key in CONCEPTS]
    length = math.sqrt(sum(x * x for x in v)) or 1
    return [x / length for x in v]


def classify(chunks: list[dict]) -> tuple[list[dict], dict]:
    support: dict[str, list[str]] = {}
    for chunk in chunks:
        for key in concepts(chunk["text"]):
            support.setdefault(key, []).append(chunk["citation_id"])
    categories = [
        {"category": label, "citation_ids": sorted({c for k in keys for c in support.get(k, [])}),
         "method": "documented_concept_match", "version": VERSION}
        for label, keys in CATEGORIES.items() if any(k in support for k in keys)
    ]
    facets = {field: [{"value": k, "citation_ids": sorted(set(support[k]))} for k in keys if k in support]
              for field, keys in FACETS.items()}
    return categories, facets


def interpret(query: str, catalog: list[dict]) -> dict:
    found = concepts(query)
    ids = [p["inv_id"] for p in catalog if matches(query, p["inv_id"])
           or (p.get("acronym") and matches(query, p["acronym"]))]
    # Longest acronym wins when FLEX-II and FLEX occur together as nested aliases.
    ids = list(dict.fromkeys(ids))
    intent = "search"
    for key, aliases in [("compare", ["compara", "compare", "diferencias"]),
                         ("summarize", ["resume", "resumen", "summarize"]),
                         ("recommend", ["recomienda", "recommend"]),
                         ("interpret", ["demuestra", "resultados", "conclusiones", "exacta", "exact"] )]:
        if any(matches(query, a) for a in aliases):
            intent = key
            break
    quantities = {}
    patterns = {
        "o2_pct": r"(\d+(?:[.,]\d+)?)\s*%\s*(?:de\s*)?(?:o2|oxigeno|oxygen)",
        "pressure_kpa": r"(\d+(?:[.,]\d+)?)\s*kpa\b",
        "flow_cm_s": r"(\d+(?:[.,]\d+)?)\s*cm\s*/\s*s\b",
        "gravity_g": r"(\d+(?:[.,]\d+)?)\s*g\b",
    }
    text = normalize(query)
    for name, pattern in patterns.items():
        m = re.search(pattern, text)
        quantities[name] = float(m[1].replace(",", ".")) if m else None
    return {"query": query, "intent": intent, "investigation_ids": ids, "concepts": found,
            **{k: [x for x in keys if x in found] for k, keys in FACETS.items()},
            "environment": next((k for k in ["lunar_base", "mars_base", "space_station", "spacecraft",
                                             "pressurized_vehicle"] if k in found), None),
            "quantities": quantities, "parser": VERSION}


def lexical_score(query: str, text: str) -> float:
    q = tokens(query)
    return len(q & tokens(text)) / max(1, len(q))
