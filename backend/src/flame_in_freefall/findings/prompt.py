"""Extraction prompt + forced-JSON output schema (versioned; hashed into every run).

The LLM copies text, it does not interpret numbers: numeric fields are returned
as ``value_text`` exactly as written plus the unit as written; parsing and unit
conversion happen later in deterministic verification (M2 parsers/registry).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

PROMPT_VERSION = "p-6"

_TEXT_COND = {"type": ["object", "null"], "properties": {"value": {"type": "string"}, "quote": {"type": "string"}},
              "required": ["value", "quote"], "additionalProperties": False}
_NUM = {"type": "object", "properties": {"value_text": {"type": "string"}, "unit": {"type": ["string", "null"]},
                                          "quote": {"type": "string"}},
        "required": ["value_text", "unit", "quote"], "additionalProperties": False}
_NUM_COND = {**_NUM, "type": ["object", "null"]}

TEXT_CONDITIONS = ("fuel", "phase", "geometry")
NUMERIC_CONDITIONS = ("o2", "pressure", "flow_velocity", "gravity_g")
CLAIM_TYPES = ("result", "future_work", "limitation")
DIRECTIONS = ("increase", "decrease", "non_monotonic", "threshold", "none")
HAZARD_STAGES = ("prevention", "detection", "suppression")
ATTRIBUTIONS = ("this_work", "cited_work", "unclear")
FINDING_KINDS = CLAIM_TYPES
TARGET_KINDS = (*CLAIM_TYPES, "method", "background", "caption", "other")

FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claim": {"type": "string"},
        "claim_quote": {"type": "string"},
        "claim_type": {"enum": list(CLAIM_TYPES)},
        "attribution": {"enum": list(ATTRIBUTIONS)},
        "variable": {"type": ["string", "null"]},
        "effect_on": {"type": ["string", "null"]},
        "direction": {"enum": [*DIRECTIONS, None]},
        "conditions": {
            "type": "object",
            "properties": {**{k: _TEXT_COND for k in TEXT_CONDITIONS}, **{k: _NUM_COND for k in NUMERIC_CONDITIONS}},
            "required": [*TEXT_CONDITIONS, *NUMERIC_CONDITIONS],
            "additionalProperties": False,
        },
        "values": {"type": "array", "maxItems": 8,
                   "items": {**_NUM, "properties": {"quantity": {"type": "string"}, **_NUM["properties"]},
                             "required": ["quantity", *_NUM["required"]]}},
        "measurement": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
        "hazard_stage": {"enum": [*HAZARD_STAGES, None]},
        "open_facets": {"type": "array", "maxItems": 6,
                        "items": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "string"},
                                                                     "quote": {"type": "string"}},
                                  "required": ["name", "value", "quote"], "additionalProperties": False}},
    },
    "required": ["claim", "claim_quote", "claim_type", "attribution", "variable", "effect_on", "direction", "conditions", "values",
                 "measurement", "hazard_stage", "open_facets"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    # target_kinds FIRST: the grammar emits properties in order, so the model classifies before extracting (p-6)
    "properties": {"target_kinds": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"enum": list(TARGET_KINDS)}},
                   "findings": {"type": "array", "maxItems": 5, "items": FINDING_SCHEMA}},
    "required": ["target_kinds", "findings"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You extract atomic scientific findings from combustion-science documents (NASA PSI).
A finding is one verifiable statement of exactly one of these types:
- result: an outcome about the combustion phenomena, fuels or materials that the authors OBSERVED, MEASURED or
  COMPUTED in this work (e.g. a flame spread rate, an extinction limit, a trend, a comparison with a model).
- limitation: anything that limits, qualifies or reduces the evidence of this work: data loss or corruption,
  contamination, hardware anomalies or failures that affected the data, a reduced or partial test matrix, a data
  selection criterion ("only runs where ... are reported"), measurement uncertainty, unresolved disagreement with
  predictions, assumptions. A problem that happened to the experiment is a limitation, not a result.
- future_work: an explicit proposal, recommendation or stated need for further work ("should", "would require",
  "future experiments", "needs to be studied", an open question the authors pose). Expected benefits or
  motivation ("may improve understanding of ...") are NOT future_work.
NOT findings (return no finding for them, even inside a Results section):
- background, motivation, purpose, expected benefits, general knowledge;
- methods: what the apparatus, hardware, setup, procedure, testing or test matrix consisted of, or what was done
  (e.g. "functional testing was performed", "samples were ignited with a hot wire");
- programmatic or operational history that does not affect the evidence (schedules, launches, objectives changed);
- figure and table captions.
attribution: "this_work" when the statement reports this document's own work; "cited_work" when it reports other
studies (reference markers such as [12], superscript numbers, "(Smith et al., 2005)", "previous studies showed",
"has been reported"); "unclear" when it cannot be decided from the text. Never attribute cited statements to this
work. A cited statement is a finding only if the authors use it as evidence; otherwise it is background.

Step 1 - classify the TARGET first. target_kinds lists every kind of content the TARGET contains (one or more):
- result, limitation, future_work: as defined above;
- method: apparatus, setup, procedure, testing performed, analysis procedure, data handling, instructions;
- background: motivation, purpose, expected benefits, general knowledge, cited work used as background;
- caption: figure or table caption, or a description of what an image or plot shows;
- other: equations, headings, lists, administrative or operational text, requests, fragments.
Step 2 - extract findings ONLY for the kinds result, limitation and future_work that you listed in target_kinds.
Every finding's claim_type must appear in target_kinds. If target_kinds has none of those three kinds, findings
must be []: that is the correct answer for methods, background, captions and other text.

Rules:
1. Extract findings ONLY from the TARGET text. BEFORE/AFTER are context to understand it; quote them only if the
   TARGET statement continues there. A finding stated only in BEFORE or AFTER belongs to another unit: skip it.
2. Every quote must be copied verbatim, character for character, as one contiguous span of the given text.
   Do not fix spelling, do not drop or reword words inside the span (keep "Furthermore,", hyphenated line breaks
   such as "densi- ties", quotation marks and symbols as written), do not join separate passages, do not add
   ellipses.
3. Never infer or assume a condition, number or unit that is not written in the text. If it is not stated, use null.
   Do not use knowledge about the mission, the investigation or typical experiments to fill fields.
4. Numbers: copy value_text exactly as written (ranges and approximations included, e.g. "21-40", "~0.5") and the
   unit exactly as written (or null if no unit is written). Do not convert units. gravity_g only if a numeric
   gravity level is written; words like "microgravity" go to open_facets as name "gravity_regime", never to phase.
   phase is the physical state of the fuel (solid, liquid, gas); geometry is the sample shape (droplet, rod, sheet).
5. claim: a short, self-contained English sentence faithful to the quote; no information beyond the quotes.
6. direction: effect of `variable` on `effect_on` only when the text states a direction; otherwise null.
7. One sentence may contain several findings of different types (for example a result and the limitation that
   qualifies it, or a result followed by a proposal). Extract each one as a separate finding. Its claim_quote is
   the shortest contiguous span that supports THAT finding (the clause, not the whole sentence, when the sentence
   holds several findings); quotes of different findings may overlap.
8. Never output the same finding twice: every finding must differ in claim_type or in what it states. When every
   finding in the TARGET has been listed, close the JSON.
9. If the TARGET contains no finding, findings is []. That is correct for methods, background, captions and other.
Return JSON only."""

USER_TEMPLATE = """Document: {doc_title}
Section: {section_title}

BEFORE:
{before}

TARGET:
{target}

AFTER:
{after}"""


def render_user(unit: dict[str, Any], template: str | None = None) -> str:
    ctx, t0, t1 = unit["context_text"], unit["target_start"], unit["target_end"]
    return (template or USER_TEMPLATE).format(
        doc_title=unit.get("doc_title") or "(untitled)",
        section_title=unit.get("section_title") or "(none)",
        before=ctx[:t0].strip() or "(none)",
        target=ctx[t0:t1],
        after=ctx[t1:].strip() or "(none)",
    )


def prompt_bundle() -> dict[str, Any]:
    body = {"version": PROMPT_VERSION, "system": SYSTEM_PROMPT, "user_template": USER_TEMPLATE,
            "output_schema": OUTPUT_SCHEMA}
    body["sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body
