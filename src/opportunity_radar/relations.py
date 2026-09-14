"""Only supplied, evidenced edges may form transmission paths."""
from collections import defaultdict

from src.opportunity_radar.contracts import digest, visible
from src.opportunity_radar.company_evidence import RELATION_TYPES as ECONOMIC_TYPES, valid_relation

RELATION_TYPES = set("PRODUCER CONSUMER PRICE_BENEFICIARY COST_BENEFICIARY COST_VICTIM EQUIPMENT_SUPPLIER MATERIAL_SUPPLIER SERVICE_PROVIDER DOWNSTREAM_DEMAND SUBSTITUTE COMPLEMENTARY".split())
RELATION_TYPES |= ECONOMIC_TYPES


def merge_relations(edges):
    result = {}
    for edge in sorted(edges, key=lambda r: r["first_seen_at"]):
        key = digest({k: edge.get(k) for k in ("from", "to", "stock_code", "relationship_type", "evidence", "url", "published_at", "parser_version", "relation_status")})
        result.setdefault(key, edge)
    return list(result.values())


def transmission_paths(edges, cutoff):
    graph = defaultdict(list)
    for edge in merge_relations(edges):
        if edge.get("relation_status") and not valid_relation(edge):
            continue
        if edge.get("relationship_type") not in RELATION_TYPES:
            raise ValueError("UNKNOWN_RELATIONSHIP_TYPE")
        if not visible(edge, cutoff) or not edge.get("provenance") or not (edge.get("url") or edge.get("source_path")):
            continue
        if not edge.get("from") or not edge.get("to"):
            raise ValueError("RELATION_ENDPOINT_REQUIRED")
        graph[edge["from"]].append(edge)
    output = []
    def walk(origin, current, visited, path):
        if len(path) == 3:
            return
        for edge in graph[current]:
            end = edge["to"]
            if end in visited:
                continue
            chain = path + [edge]
            output.append({"variable": origin, "upstream_theme": origin, "downstream_theme": end,
                           "stock_code": edge.get("stock_code"), "relationship_type": edge["relationship_type"],
                           "transmission_depth": len(chain), "revenue_exposure": edge.get("revenue_exposure"),
                           "cost_exposure": edge.get("cost_exposure"), "production_exposure": edge.get("production_exposure"),
                           "source": [e.get("url") or e.get("source_path") for e in chain],
                           "confidence": min((e.get("confidence", 0) for e in chain)),
                           "evidence": [digest(e) for e in chain],
                           "product": edge.get("product"), "stock_name": edge.get("stock_name") or edge.get("company_name"),
                           "profit_exposure": edge.get("profit_exposure"), "customer_exposure": edge.get("customer_exposure"),
                           "capacity_exposure": edge.get("capacity_exposure"), "relation_status": edge.get("relation_status", "VERIFIED"),
                           "evidence_dates": [e.get("evidence_date") or e.get("source_date") for e in chain],
                           "transmission_semantics": "EVIDENCED_EXPOSURE_PATH_NOT_DEMAND_OR_EARNINGS_CAUSAL_PROOF"})
            # A company's own-product disclosure is terminal exposure evidence.
            # Shared products do not prove company-to-company supply relationships.
            if not edge.get("stock_code") and edge["relationship_type"] not in {"PRODUCER", "core_producer"}:
                walk(origin, end, visited | {end}, chain)
    for origin in list(graph):
        walk(origin, origin, {origin}, [])
    return output
