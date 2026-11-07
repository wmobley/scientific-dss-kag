#!/usr/bin/env python3
"""Ask KAG's solver one question (use the KAG virtualenv's python, from the KAG project directory):

    cd work/kag/project/GwSubsidence && ../../.venv/bin/python ../../../../scripts/kag_query.py "question" [trace.json]

Prints JSON: the answer, the trace's top-level keys and every evidence ID (ev-...) that appears anywhere in
the trace. The full trace can be written to a file for inspection (it can contain passage text).
"""
import asyncio
import json
import os
import re
import sys

EVIDENCE_ID = re.compile(r"\bev-[a-z0-9-]+\b")


def ids_in(node, found):
    if isinstance(node, dict):
        for key, value in node.items():
            ids_in(key, found)
            ids_in(value, found)
    elif isinstance(node, (list, tuple)):
        for item in node:
            ids_in(item, found)
    elif isinstance(node, str):
        found.update(EVIDENCE_ID.findall(node))
    return found


async def ask(query):
    from kag.common.conf import KAG_CONFIG
    from kag.common.registry import import_modules_from_path
    from kag.interface import SolverPipelineABC
    from kag.solver.reporter.trace_log_reporter import TraceLogReporter

    if os.path.isdir("./prompt"):  # project-specific prompts, if the project defines any
        import_modules_from_path("./prompt")
    reporter = TraceLogReporter()
    pipeline = SolverPipelineABC.from_config(KAG_CONFIG.all_config["kag_solver_pipeline"])
    answer = await pipeline.ainvoke(query, reporter=reporter)
    info, _status = reporter.generate_report_data()
    return answer, info.to_dict()


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    answer, trace = asyncio.run(ask(sys.argv[1]))
    if len(sys.argv) == 3:
        with open(sys.argv[2], "w") as handle:
            json.dump(trace, handle, default=str, indent=1)
    print(json.dumps({"query": sys.argv[1], "answer": answer if isinstance(answer, str) else str(answer),
                      "trace_keys": sorted(trace) if isinstance(trace, dict) else None,
                      "evidence_ids_in_trace": sorted(ids_in(trace, set()))}, indent=1))
