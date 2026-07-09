#!/usr/bin/env python
"""dossier — an /investigate case file -> report + relationship graph + timeline.

Reads a JSON case file (the structured selectors the /investigate loop
accumulates), builds a provenance graph with networkx (which module/seed produced
which fact), and emits a markdown report, a GraphML graph, and a timeline.

Case file format (see README):
    {"target": "Jane Doe", "facts": [
        {"type": "email", "value": "a@b.com", "source": "dehashed",
         "confidence": "high", "date": "2021-03-04"}, ...]}
A bare JSON list of fact objects is also accepted.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import networkx as nx


def load_facts(case):
    if isinstance(case, list):
        return case, "target"
    return case.get("facts", []), case.get("target", "target")


def build_graph(facts, target):
    # ponytail: provenance graph only (source -> fact, target -> fact). Inferring
    # fact-to-fact links is a heuristic guess; export GraphML and let a human/Gephi
    # draw conclusions rather than bake in a wrong edge.
    g = nx.DiGraph()
    g.add_node(target, kind="target")
    for f in facts:
        val, src = f["value"], f.get("source", "unknown")
        g.add_node(val, kind="fact", type=f.get("type", ""), confidence=f.get("confidence", ""))
        g.add_node(src, kind="source")
        g.add_edge(src, val)      # this source produced this fact
        g.add_edge(target, val)   # this fact belongs to the target
    return g


def report_md(facts, target):
    by_type = defaultdict(list)
    for f in facts:
        by_type[f.get("type", "other")].append(f)
    lines = [f"# Dossier: {target}", "",
             f"{len(facts)} facts across {len(by_type)} types.", ""]
    for t in sorted(by_type):
        lines.append(f"## {t} ({len(by_type[t])})")
        for f in by_type[t]:
            conf = f.get("confidence", "")
            conf = f" _(confidence: {conf})_" if conf else ""
            lines.append(f"- **{f['value']}** — via `{f.get('source', 'unknown')}`{conf}")
        lines.append("")
    return "\n".join(lines)


def timeline_md(facts, target):
    dated = sorted((f for f in facts if f.get("date")), key=lambda f: f["date"])
    lines = [f"# Timeline: {target}", ""]
    if not dated:
        lines.append("_No dated facts._")
    for f in dated:
        lines.append(f"- **{f['date']}** — {f.get('type', '')}: {f['value']} "
                     f"(via `{f.get('source', 'unknown')}`)")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build a dossier from an /investigate case file.")
    ap.add_argument("--case", help="Path to the JSON case file.")
    ap.add_argument("--out", help="Output directory (default: next to the case file).")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.case:
        ap.error("--case is required (or --selftest)")
    with open(args.case, encoding="utf-8") as fh:
        case = json.load(fh)
    facts, target = load_facts(case)
    out = args.out or os.path.dirname(os.path.abspath(args.case))
    os.makedirs(out, exist_ok=True)
    g = build_graph(facts, target)
    nx.write_graphml(g, os.path.join(out, "graph.graphml"))
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(report_md(facts, target))
    with open(os.path.join(out, "timeline.md"), "w", encoding="utf-8") as fh:
        fh.write(timeline_md(facts, target))
    print(f"dossier -> {out}")
    print(f"  report.md  timeline.md  graph.graphml  "
          f"({g.number_of_nodes()} nodes, {g.number_of_edges()} edges)")
    return 0


def selftest():
    facts = [
        {"type": "email", "value": "jane@x.com", "source": "user", "date": "2020-01-02"},
        {"type": "hashed_password", "value": "abc123", "source": "dehashed", "date": "2021-05-06"},
        {"type": "password", "value": "hunter2", "source": "pw-cracker"},
    ]
    g = build_graph(facts, "Jane Doe")
    # target + 3 facts + 3 sources (user, dehashed, pw-cracker) = 7 nodes
    assert g.number_of_nodes() == 7, g.number_of_nodes()
    assert g.has_edge("dehashed", "abc123"), "provenance edge"
    assert g.has_edge("Jane Doe", "hunter2"), "target edge"
    tl = timeline_md(facts, "Jane Doe")
    assert tl.index("2020-01-02") < tl.index("2021-05-06"), "timeline not sorted"
    assert "hunter2" not in tl, "undated fact leaked into timeline"
    rep = report_md(facts, "Jane Doe")
    assert "## email (1)" in rep and "hunter2" in rep, rep
    print("dossier selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
