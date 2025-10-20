# Pipeline architecture

Edgar implements a JSON-based packet protocol enabling composable command
chains like `select filings | probe roles | update facts`. Each command receives
structured data from stdin and outputs to stdout, with main.py orchestrating
packet flow and format detection (table for terminal, JSON for pipes). The
pipeline carries provenance information, tracking the complete command sequence
for journaling purposes. This architecture enables progressive disclosure
workflows where users iteratively explore and refine their data queries.
