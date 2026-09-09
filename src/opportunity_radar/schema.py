"""Schema generated from the same category contract used by normalization."""
from src.opportunity_radar.contracts import CATEGORIES, FIELDS, VERSION

EXTRA_SECTIONS = "market_context technology_supply_chain_mapping industry_transmission_mapping theme_candidates company_specific_candidates positive_change_candidates negative_risk_candidates factor41_mapping signal_history lead_time_statistics data_gaps source_manifest".split()


def schema():
    nullable = {"type": ["string", "null"]}
    props = {key: nullable for key in "entity theme stock_code stock_name metric unit currency event_date published_at first_seen_at effective_date source_date source source_path url body_evidence title".split()}
    props.update({"observation_id": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                  "signal_type": {"enum": list(CATEGORIES)}, "source_tier": {"enum": [1, 2, 3, 4]},
                  "value": {"type": ["number", "null"]}, "facts": {"type": "object"},
                  "provenance": {"type": ["object", "null"]}, "data_quality": {"enum": ["PASS", "PARTIAL", "UNAVAILABLE", "LOW_CONFIDENCE"]},
                  "confidence": {"enum": ["LOW", "HIGH"]}, "data_gaps": {"type": "array", "items": {"type": "string"}},
                  "as_of_valid": {"const": True}, "mapped_factor_ids": {"type": "array", "uniqueItems": True, "items": {"type": "integer", "minimum": 1, "maximum": 41}},
                  "mapping_confidence": {"const": "LOW"}, "mapping_method": {"const": "CATEGORY_ASSOCIATION_NOT_CAUSAL"},
                  "mapping_source": {"type": "string"}, "changes": {"type": "object"},
                  "history_references": {"type": "array", "items": {"type": "string"}}})
    observation = {"type": "object", "required": list(props), "additionalProperties": False, "properties": props,
                   "allOf": [{"if": {"properties": {"signal_type": {"const": key}}},
                              "then": {"properties": {"facts": {"required": fields.split()}}}} for key, fields in FIELDS.items()]}
    top = {name: {"type": "array", "items": {"$ref": "#/$defs/observation"}} for name in CATEGORIES.values()}
    for name in EXTRA_SECTIONS:
        top[name] = {"type": "object" if name in {"market_context", "technology_supply_chain_mapping", "lead_time_statistics"} else "array"}
    candidate = {"type": "object", "required": ["entity", "theme", "stock_code", "candidate_type", "signal_type", "observation_id", "signal_first_seen_date", "source_date", "direction", "changes", "first_seen_at"],
                 "properties": {"entity": nullable, "theme": nullable, "stock_code": nullable,
                                "candidate_type": {"enum": ["THEME_LEVEL_CANDIDATE", "COMPANY_SPECIFIC_CANDIDATE"]},
                                "signal_type": {"enum": list(CATEGORIES)}, "observation_id": props["observation_id"],
                                "signal_first_seen_date": {"type": "string"}, "source_date": {"type": "string"},
                                "direction": {"enum": ["INCREASE", "DECREASE"]}, "changes": {"type": "object"},
                                "first_seen_at": {"type": "string"}}}
    for key in ("theme_candidates", "company_specific_candidates", "positive_change_candidates", "negative_risk_candidates"):
        top[key]["items"] = candidate
    top["lead_time_statistics"]["required"] = ["records", "status"]
    top["lead_time_statistics"]["properties"] = {"records": {"type": "array", "items": {
        "type": "object", "required": ["entity", "signal_type", "lead_trading_days"],
        "properties": {"entity": nullable, "signal_type": {"enum": list(CATEGORIES)}, "lead_trading_days": {"type": ["integer", "null"]}}}}}
    top["source_manifest"]["items"] = {"type": "object", "required": ["path", "url", "source", "provenance", "source_tier"],
                                       "properties": {"path": nullable, "url": nullable, "source": nullable,
                                                      "provenance": {"type": "object", "required": ["sha256"], "properties": {"sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}},
                                                      "source_tier": {"enum": [1, 2, 3, 4]}}}
    top["meta"] = {"type": "object", "required": ["schema_version", "trade_date", "snapshot_type", "as_of", "data_role", "final_judgement_owner", "execution_mode"], "properties": {
        "schema_version": {"const": VERSION}, "trade_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "snapshot_type": {"enum": ["MORNING", "EOD"]}, "as_of": {"type": "string"},
        "data_role": {"const": "OBJECTIVE_OPPORTUNITY_EVIDENCE"}, "final_judgement_owner": {"const": "chatgpt"},
        "execution_mode": {"enum": ["LIVE", "AS_OF_REPLAY"]},
    }, "additionalProperties": False}
    top["compact_metadata"] = {"type": "object"}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": VERSION,
            "type": "object", "required": [k for k in top if k != "compact_metadata"],
            "additionalProperties": False, "properties": top, "$defs": {"observation": observation}}
