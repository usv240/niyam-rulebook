"""Command line: python -m niyam_rulebook <check|test|simulate|rules|snapshot>."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from .engine import ROOT, Rulebook


def run_tests(rb: Rulebook, only: str | None = None) -> dict[str, Any]:
    results = {"passed": 0, "failed": 0, "failures": []}
    for path in sorted((rb.root / "tests").rglob("*.yaml")):
        suite = yaml.safe_load(path.read_text(encoding="utf-8"))
        sid = suite["scheme"]
        if only and sid != only:
            continue
        for case in suite.get("cases", []):
            try:
                out = rb.evaluate(case["person"], case["date"], schemes=[sid])[sid]
                problems = []
                for key, want in case["expect"].items():
                    if out.get(key) != want:
                        problems.append(f"{key}: expected {want!r}, got {out.get(key)!r}")
            except Exception as e:  # a broken rule file must fail the test, not crash the run
                problems, out = [f"error: {e}"], {}
            if problems:
                results["failed"] += 1
                unmet = [r["id"] for r in out.get("reasons", []) if not r["met"]]
                results["failures"].append({"file": str(path.relative_to(rb.root)), "case": case["name"],
                                            "problems": problems, "unmet_conditions": unmet,
                                            "source": case.get("source")})
            else:
                results["passed"] += 1
    return results


def snapshot(rb: Rulebook) -> dict[str, Any]:
    """Everything the website and API need, including full history."""
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "sources": rb.sources,
           "person_schema": rb.person_schema, "schemes": {}}
    for sid, s in rb.schemes.items():
        out["schemes"][sid] = {
            **{k: v for k, v in s.data.items() if k != "conditions"},
            "launched": str(s.data["launched"]),
            "conditions": [
                {"id": c.id, "text": c.text, "when": c.when, "kind": c.kind, "source": c.source,
                 "valid_from": c.valid_from.isoformat(),
                 "valid_until": c.valid_until.isoformat() if c.valid_until else None}
                for c in s.conditions
            ],
            "parameters": {
                name: {"description": p.description, "unit": p.unit,
                       "values": [{"start": v.start.isoformat(), "value": v.value, "reference": v.reference}
                                  for v in p.values]}
                for name, p in s.params.items()
            },
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="niyam_rulebook")
    ap.add_argument("--root", default=str(ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate rule files")
    t = sub.add_parser("test", help="run test citizens")
    t.add_argument("--scheme")
    t.add_argument("--json", action="store_true")
    s = sub.add_parser("simulate", help="evaluate one person")
    s.add_argument("person", help="JSON object, or @file.json")
    s.add_argument("--date")
    sb = sub.add_parser("simulate-batch", help="evaluate many cases from a JSON list file")
    sb.add_argument("file", help="JSON list of {person, date, scheme}")
    r = sub.add_parser("rules", help="show the rules of a scheme on a date")
    r.add_argument("scheme")
    r.add_argument("--date")
    sn = sub.add_parser("snapshot", help="write the full rulebook as JSON")
    sn.add_argument("--out")
    args = ap.parse_args(argv)

    rb = Rulebook(Path(args.root))
    if args.cmd == "check":
        problems = rb.check()
        for p in problems:
            print(f"PROBLEM {p}")
        print("check: ok" if not problems else f"check: {len(problems)} problem(s)")
        return 1 if problems else 0
    if args.cmd == "test":
        problems = rb.check()
        res = run_tests(rb, args.scheme)
        res["check_problems"] = problems
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            for p in problems:
                print(f"PROBLEM {p}")
            for f in res["failures"]:
                print(f"FAIL {f['file']} :: {f['case']}")
                for p in f["problems"]:
                    print(f"     {p}")
                if f["unmet_conditions"]:
                    print(f"     unmet conditions: {', '.join(f['unmet_conditions'])}")
            print(f"tests: {res['passed']} passed, {res['failed']} failed")
        return 1 if (res["failed"] or problems) else 0
    if args.cmd == "simulate":
        raw = Path(args.person[1:]).read_text(encoding="utf-8") if args.person.startswith("@") else args.person
        print(json.dumps(rb.evaluate(json.loads(raw), args.date), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "simulate-batch":
        out = []
        for case in json.loads(Path(args.file).read_text(encoding="utf-8")):
            try:
                res = rb.evaluate(case["person"], case.get("date"), schemes=[case["scheme"]] if case.get("scheme") else None)
                out.append({"ok": True, "result": res})
            except Exception as e:  # report bad cases instead of failing the batch
                out.append({"ok": False, "error": str(e)})
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if args.cmd == "rules":
        print(json.dumps(rb.rules_at(args.scheme, args.date), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.cmd == "snapshot":
        text = json.dumps(snapshot(rb), ensure_ascii=False, indent=2, default=str)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
