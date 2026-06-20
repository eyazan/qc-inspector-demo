"""Smoke test for spec resolution: SAP source + the Section 3 lookup strategy.

Exercises the lookup chain (SAP -> local store -> fuzzy -> single-file index ->
clear error) against the local spec store. With SPEC_SOURCE=local no live SAP is
called. Ensure the spec store is populated first (scripts/index_specs.py --mode full).

    python scripts/test_sap_spec.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.factory import get_spec_lookup_strategy, get_spec_store  # noqa: E402
from app.services.spec_indexing_service import SpecIndexingService  # noqa: E402


def main() -> int:
    print("== Ensuring spec store is populated ==")
    SpecIndexingService().run(mode="incremental")

    store = get_spec_store()
    print("Indexed specs:", [s["spec_no"] for s in store.list_specs()])

    strat = get_spec_lookup_strategy()
    ok = True

    r = strat.resolve(extra_specs=["AMS4911"])
    print(f"exact   -> status={r.status} source={r.source} spec={r.spec_no} sections={len(r.sections)}")
    ok &= r.status == "found" and r.source == "local_store_exact"

    r = strat.resolve(extra_specs=["AMS 4911X"])
    print(f"fuzzy   -> status={r.status} source={r.source} spec={r.spec_no}")
    ok &= r.status == "found"

    r = strat.resolve(extra_specs=["NONEXIST-9999"])
    print(f"missing -> status={r.status} stage={r.stage}")
    ok &= r.status == "not_found" and r.stage == "spec_lookup"

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
