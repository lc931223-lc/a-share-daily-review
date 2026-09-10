"""Only supplied, evidenced edges may form transmission paths."""
from collections import defaultdict

from src.opportunity_radar.contracts import digest, visible

RELATION_TYPES = set("PRODUCER CONSUMER PRICE_BENEFICIARY COST_BENEFICIARY COST_VICTIM EQUIPMENT_SUPPLIER MATERIAL_SUPPLIER SERVICE_PROVIDER DOWNSTREAM_DEMAND SUBSTITUTE COMPLEMENTARY".split())


def merge_relations(edges):
    result = {}
    for edge in sorted(edges, key=lambda r: r["first_seen_at"]):
        key = digest({k: edge.get(k) for k in ("from", "to", "stock_code", "relationship_type", "evidence", "url", "published_at")})
        result.setdefault(key, edge)
    return list(result.values())


def transmission_paths(edges, cutoff):
    graph = defaultdict(list)
    for edge in merge_relations(edges):
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
                           "evidence": [digest(e) for e in chain]})
            walk(origin, end, visited | {end}, chain)
    for origin in list(graph):
        walk(origin, origin, {origin}, [])
    return output
