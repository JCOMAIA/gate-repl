"""Belief-gate for an agent-built Tag arena (KCC + StarterAssets + Mirror, via Unity MCP).

Two corrections that make it honest and unfakeable:

  (1) The parkour graph is DERIVED from the queried node positions + player_capabilities,
      NOT trusted from agent-declared edges. An edge exists iff a player with these
      capabilities could actually make the traversal (jump/vault/wallrun reach). The agent
      cannot "satisfy" connectivity by asserting an edge it didn't build.

  (2) Invariants are split:
        STRUCTURAL → deterministic FACTS the gate guarantees (presence, distances,
                     connectivity, reachability). Pass/fail is leak-proof.
        HEURISTIC  → deterministic ESTIMATES that MODEL fun/balance (tag time, verticality,
                     density). Same input → same number, but the number is a model, not a
                     truth. Reported as warnings, never as a hard guarantee.

CRITICAL: `present` must be QUERIED from the live Unity scene (object ids, types/tags,
world positions, components) — never the agent's prose claim. That is the whole guarantee.

Demo (no Unity needed):  python tag_arena_gate.py
"""
from __future__ import annotations

import json
import math
import os
from collections import deque, Counter

TRAVERSAL = {"Platform", "VaultObstacle", "WallRunSurface", "RunnerSpawn", "ChaserSpawn"}


def load(path):
    return json.load(open(path, encoding="utf-8"))


def _hdist(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])   # horizontal (x,z)


def _reach_dx(from_node, to_node, caps):
    """Max horizontal reach for this traversal, given capabilities and the node types
    involved. Vault/wallrun assets extend reach; plain jump is the baseline."""
    dx = caps["max_jump_dx"]
    types = {from_node["type"], to_node["type"]}
    if caps.get("wallrun") and "WallRunSurface" in types:
        dx += caps.get("wallrun_extra_dx", 0.0)
    if caps.get("vault") and "VaultObstacle" in types:
        dx += caps.get("vault_extra_dx", 0.0)
    return dx


def derive_graph(nodes, caps):
    """Edge u->v iff horizontal gap within reach AND rise within jump height (down is free)."""
    adj = {n["id"]: [] for n in nodes}
    by_id = {n["id"]: n for n in nodes}
    for u in nodes:
        for v in nodes:
            if u["id"] == v["id"]:
                continue
            hd = _hdist(u["pos"], v["pos"])
            rise = v["pos"][1] - u["pos"][1]
            if hd <= _reach_dx(u, v, caps) and rise <= caps["max_jump_dy"]:
                adj[u["id"]].append(v["id"])
    return adj, by_id


def _bfs(adj, start):
    seen, q = {start}, deque([start])
    while q:
        u = q.popleft()
        for v in adj.get(u, []):
            if v not in seen:
                seen.add(v); q.append(v)
    return seen


def gate(manifest, present):
    """present: [{id, type, pos?}, ...] read from the Unity scene."""
    caps, rules = manifest["player_capabilities"], manifest["rules"]
    pres_by_id = {p["id"]: p for p in present}
    req_ids = [it["id"] for it in manifest["required"]]

    structural, heuristic = [], []

    # --- presence / ids ---
    missing = sorted(set(req_ids) - set(pres_by_id))
    if missing:
        structural.append(f"missing required objects: {missing}")
    dups = [i for i, c in Counter(p["id"] for p in present).items() if c > 1]
    if dups:
        structural.append(f"duplicate ids: {dups}")
    for need, label in [("MirrorNetworkManager", "mirror_network_manager"),
                        ("NetworkPlayer", "player_prefab"),
                        ("RunnerSpawn", "spawn_runner"), ("ChaserSpawn", "spawn_chaser")]:
        if not any(p["type"] == need for p in present):
            structural.append(f"{label} not present (type {need})")

    # --- spawn distance ---
    runner = next((p for p in present if p["type"] == "RunnerSpawn"), None)
    chaser = next((p for p in present if p["type"] == "ChaserSpawn"), None)
    if runner and chaser:
        d = _hdist(runner["pos"], chaser["pos"])
        if d < rules["minimum_spawn_distance"]:
            structural.append(f"spawn_distance {d:.1f} < min {rules['minimum_spawn_distance']}")

    # --- min vaults / wallruns ---
    nv = sum(1 for p in present if p["type"] == "VaultObstacle")
    nw = sum(1 for p in present if p["type"] == "WallRunSurface")
    if nv < rules["minimum_vaults"]:
        structural.append(f"vaults {nv} < min {rules['minimum_vaults']}")
    if nw < rules["minimum_wallruns"]:
        structural.append(f"wallruns {nw} < min {rules['minimum_wallruns']}")

    # --- derived parkour graph + connectivity/reachability (the powerful part) ---
    nodes = [p for p in present if p["type"] in TRAVERSAL and "pos" in p]
    adj, by_id = derive_graph(nodes, caps)

    isolated = [n["id"] for n in nodes if n["type"] == "Platform" and not adj[n["id"]]
                and not any(n["id"] in adj[m] for m in adj)]
    if isolated:
        structural.append(f"isolated platforms (no reachable edge given capabilities): {isolated}")

    if runner:
        reach_r = _bfs(adj, runner["id"])
        unreachable = [n["id"] for n in nodes if n["id"] not in reach_r]
        if unreachable:
            structural.append(f"runner cannot reach: {unreachable}")
        escape = len(adj[runner["id"]])
        if escape < rules["minimum_escape_routes"]:
            structural.append(f"runner escape routes {escape} < min {rules['minimum_escape_routes']}")
    if chaser:
        reach_c = _bfs(adj, chaser["id"])
        unreachable_c = [n["id"] for n in nodes if n["id"] not in reach_c]
        if unreachable_c:
            structural.append(f"chaser cannot reach: {unreachable_c}")

    # --- HEURISTIC estimates (deterministic, but a MODEL — warnings, not guarantees) ---
    levels = len({round(n["pos"][1]) for n in nodes})
    if levels < rules.get("minimum_verticality_levels", 0):
        heuristic.append(f"[estimate] verticality {levels} levels < min {rules['minimum_verticality_levels']}")
    density = (nv + nw) / max(len(nodes), 1)
    if density < 0.2:
        heuristic.append(f"[estimate] parkour density {density:.2f} low (vault+wallrun per node)")
    if runner and chaser and chaser["id"] in (_bfs(adj, runner["id"])):
        # crude pursuit estimate: graph hops chaser->runner * avg edge time at sprint
        hops = _hops(adj, chaser["id"], runner["id"])
        if hops is not None:
            est = hops * (caps["max_jump_dx"] / caps["sprint_speed"])
            if not (rules["minimum_estimated_tag_time"] <= est <= rules["maximum_estimated_tag_time"]):
                heuristic.append(f"[estimate] tag-time ~{est:.0f}s outside "
                                 f"[{rules['minimum_estimated_tag_time']},{rules['maximum_estimated_tag_time']}]")

    return {
        "complete": not structural,         # ONLY structural decides done/not-done
        "structural_failures": structural,  # guaranteed facts
        "heuristic_warnings": heuristic,     # estimates — review, don't gate hard
    }


def _hops(adj, a, b):
    seen, q = {a}, deque([(a, 0)])
    while q:
        u, d = q.popleft()
        if u == b:
            return d
        for v in adj.get(u, []):
            if v not in seen:
                seen.add(v); q.append((v, d + 1))
    return None


def format_gap(r):
    if r["complete"] and not r["heuristic_warnings"]:
        return "DONE — structural contract satisfied, no heuristic warnings."
    out = []
    if r["structural_failures"]:
        out.append("NOT DONE -- structural failures (must fix, these are guarantees):")
        out += [f"  [X] {f}" for f in r["structural_failures"]]
    else:
        out.append("Structural contract OK (done-able).")
    if r["heuristic_warnings"]:
        out.append("Heuristic warnings (estimates -- your call, not a hard gate):")
        out += [f"  [~] {w}" for w in r["heuristic_warnings"]]
    return "\n".join(out)


def _demo():
    m = load(os.path.join(os.path.dirname(__file__), "tag_arena_manifest.json"))
    full = [{"id": it["id"], "type": it["type"], **({"pos": it["pos"]} if "pos" in it else {})}
            for it in m["required"]]

    print("=" * 64 + "\nSCENE A — agent built the manifest\n" + "=" * 64)
    print(format_gap(gate(m, full)))

    print("\n" + "=" * 64 + "\nSCENE B — agent placed high_roof too far + dropped vault_02\n" + "=" * 64)
    broken = [dict(p) for p in full if p["id"] != "vault_02"]      # one vault missing
    for p in broken:
        if p["id"] == "high_roof":
            p["pos"] = [60, 18, 60]                                # unreachable: too far + too high
    print(format_gap(gate(m, broken)))
    print("\n(^ exact gap -> next instruction for the building agent; only the structural [X] block 'done')")


def run_cli(scene_path):
    """Verify a real exported scene against the manifest in this folder.
    Exit code 0 = structurally complete (loop may stop); 1 = structural gap remains."""
    import sys
    m = load(os.path.join(os.path.dirname(__file__), "tag_arena_manifest.json"))
    present = load(scene_path)
    r = gate(m, present)
    print(format_gap(r))
    sys.exit(0 if r["complete"] else 1)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:        # python tag_arena_gate.py scene_present.json
        run_cli(sys.argv[1])
    else:                         # python tag_arena_gate.py   -> built-in mock demo
        _demo()
