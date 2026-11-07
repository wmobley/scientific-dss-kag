#!/usr/bin/env python3
"""Run KAG's builder chain over an evidence CSV (idx,title,text). Use the KAG virtualenv's python,
from the KAG project directory so KAG finds the project's kag_config.yaml:

    cd work/kag/project/GwSubsidence && ../../.venv/bin/python ../../../../scripts/kag_ingest.py ../../evidence.csv
"""
import sys


def main(csv_path):
    from kag.builder.runner import BuilderChainRunner
    from kag.common.conf import KAG_CONFIG
    from kag.common.registry import import_modules_from_path

    import_modules_from_path(".")  # the project's own builder components, if any
    runner = BuilderChainRunner.from_config(KAG_CONFIG.all_config["kag_builder_pipeline"])
    runner.invoke(csv_path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
