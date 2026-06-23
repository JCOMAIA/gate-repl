"""Deterministic scene gate for an agent-built Unity level.

The agent (Claude Code via a Unity MCP) builds the scene; THIS verifies it against the
manifest — by executing checks over the QUERIED scene state, never the agent's self-report.
It returns the EXACT gap, which is the next iteration's instruction. When the gap is empty
AND the invariants pass, the loop is done — a deterministic termination condition, not the
agent's opinion that it "looks finished".

Two layers of check:
  1. PRESENCE/PLACEMENT  — required − present (set difference), plus position mismatch.
                            This is belief-gate's core (leak-proof: can't miss an absence).
  2. PLAYABILITY INVARIANTS — reachability over a jump-graph (spawn→exit, collectibles, keys).
                            A deletion-proof coverage check, not a set difference.

CRITICAL: `present` MUST come from querying the actual scene hierarchy (the structured
source), NOT from the agent saying "I placed everything". Trusting the prose self-report
reintroduces exactly the false-pass the gate exists to remove.

Run the built-in demo (no Unity needed):
  python scene_gate.py
"""
from __future__ import annotations

import json
import math
import os
from collections import deque

# Use the real belief-gate set-difference if available; fall back to a local one.
try:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "beliefgate"))
    from beliefgate import check_set, Verdict  # noqa
    def _missing(required, present):
        res = check_set(required=set(required), present=set(present) & set(required))
        return sorted(res.missing) if res.verdict is not Verdict.COMPLETE else []
except Exception:  # noqa: BLE001 — example must run without the lib installed
    def _missing(required, present):
        return sorted(set(required) - set(present))


def load_manifest(path):
    return json.load(open(path, encoding="utf-8"))


def _dist_ok(a, b, rules):
    """Can a player jump from foothold a to foothold b? (dx within reach; up within jump
    height; down is free.)"""
    dx = abs(a[0] - b[0]); dy = b[1] - a[1]
    return dx <= rules["max_jump_dx"] and dy <= rules["max_jump_dy"]


def _footings(manifest, present_by_id):
    """Standable nodes: spawn, exit, and every present Platform top. Items inherit the
    foothold of the platform they stand on."""
    nodes = {}
    for it in manifest["required"]:
        if it["id"] not in present_by_id:
            continue
        if it["type"] in ("PlayerSpawn", "LevelExit", "Platform"):
            nodes[it["id"]] = tuple(present_by_id[it["id"]]["pos"])
    return nodes


def _reachable_from_spawn(manifest, present_by_id, rules):
    nodes = _footings(manifest, present_by_id)
    if "spawn" not in nodes:
        return set()
    # build jump-graph over footholds, BFS from spawn
    adj = {n: [] for n in nodes}
    for u in nodes:
        for v in nodes:
            if u != v and _dist_ok(nodes[u], nodes[v], rules):
                adj[u].append(v)
    seen, q = {"spawn"}, deque(["spawn"])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in seen:
                seen.add(v); q.append(v)
    return seen


def _item_foothold(it):
    """For a collectible/key, the platform id it stands on (its reachability proxy)."""
    return it.get("stands_on")


def gate(manifest, present):
    """present: list of {id, type, pos} read from the SCENE. Returns a structured gap."""
    present_by_id = {p["id"]: p for p in present}
    req_ids = [it["id"] for it in manifest["required"]]
    rules = manifest["rules"]
    tol = rules["pos_tolerance"]

    # 1. presence (belief-gate set difference)
    missing = _missing(req_ids, list(present_by_id.keys()))

    # 1b. placement (present but wrong position) — catches "misselection" if pos is specified
    misplaced = []
    for it in manifest["required"]:
        p = present_by_id.get(it["id"])
        if p and "pos" in it:
            d = math.dist(it["pos"], p["pos"])
            if d > tol:
                misplaced.append({"id": it["id"], "expected": it["pos"], "got": p["pos"], "off_by": round(d, 2)})

    # 2. playability invariants (reachability)
    reach = _reachable_from_spawn(manifest, present_by_id, rules)
    inv = []
    if "spawn_reaches_exit" in manifest["invariants"]:
        if "exit" not in reach:
            inv.append("exit not reachable from spawn (jump-graph disconnected)")
    if "all_collectibles_reachable" in manifest["invariants"]:
        for it in manifest["required"]:
            if it["type"] in ("Coin",) and it["id"] in present_by_id:
                if _item_foothold(it) not in reach:
                    inv.append(f"collectible {it['id']} unreachable (foothold {_item_foothold(it)} not reachable)")
    if "every_door_has_reachable_key" in manifest["invariants"]:
        for it in manifest["required"]:
            if it["type"] == "Door":
                key = it.get("props", {}).get("opens_with")
                kit = next((x for x in manifest["required"] if x["id"] == key), None)
                if kit and _item_foothold(kit) not in reach:
                    inv.append(f"door {it['id']} needs key {key}, but {key} is unreachable")

    complete = not missing and not misplaced and not inv
    return {
        "complete": complete,
        "missing": missing,
        "misplaced": misplaced,
        "invariant_failures": inv,
    }


def format_gap(report):
    """Turn the gap into a precise instruction for the next agent iteration."""
    if report["complete"]:
        return "DONE — scene satisfies the manifest (presence + placement + playability)."
    lines = ["NOT DONE. Fix exactly this and rebuild:"]
    if report["missing"]:
        lines.append(f"  • place missing objects: {report['missing']}")
    for m in report["misplaced"]:
        lines.append(f"  • move {m['id']} to {m['expected']} (currently {m['got']}, off by {m['off_by']})")
    for f in report["invariant_failures"]:
        lines.append(f"  • playability: {f}")
    return "\n".join(lines)


# --------------------------- runnable demo (no Unity) ---------------------------
def _demo():
    manifest = load_manifest(os.path.join(os.path.dirname(__file__), "level_manifest.json"))
    full = [{"id": it["id"], "type": it["type"], "pos": it["pos"]} for it in manifest["required"]]

    print("=" * 64)
    print("SCENE A — agent built everything per manifest")
    print("=" * 64)
    print(format_gap(gate(manifest, full)))

    print("\n" + "=" * 64)
    print("SCENE B — agent forgot plat_f and misplaced coin_2 (the silent 'looks done')")
    print("=" * 64)
    broken = [p for p in full if p["id"] != "plat_f"]              # drop a platform
    for p in broken:
        if p["id"] == "coin_2":
            p["pos"] = [24, 14]                                    # wrong spot
    print(format_gap(gate(manifest, broken)))
    print("\n(^ this exact gap is the next instruction fed back to the building agent)")


if __name__ == "__main__":
    _demo()
