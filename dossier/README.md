# dossier  (Python, networkx)

An `/investigate` case file → a markdown **report**, a **relationship graph**
(GraphML), and a **timeline**. Reads the structured facts the investigate loop
accumulates and turns them into artifacts you can read or open in Gephi/Cytoscape.

```bash
poetry run python dossier/dossier.py --case investigations/jane.json --out investigations/jane_dossier
poetry run python dossier/dossier.py --selftest
```

Writes `report.md`, `timeline.md`, `graph.graphml` to `--out` (defaults to the
case file's own directory).

## Case file format

```json
{
  "target": "Jane Doe",
  "facts": [
    {"type": "email", "value": "jane@x.com", "source": "user",
     "confidence": "high", "date": "2019-06-01"},
    {"type": "phone", "value": "+16502530000", "source": "dehashed"}
  ]
}
```

A bare JSON list of fact objects is also accepted. Only `value` is required per
fact; `type`, `source`, `confidence`, `date` are optional. Facts with a `date`
appear on the timeline.

- **Consumes:** an investigate case file (JSON)
- **Emits:** report.md, timeline.md, graph.graphml
- **Cost:** free, offline
- **Note:** the graph is provenance-only (source → fact, target → fact). It does
  not guess fact-to-fact links; export it and let a human draw those.
