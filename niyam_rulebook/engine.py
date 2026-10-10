"""Niyam rulebook engine.

Rules live in YAML so that people and agents can read and review them:

- ``schema/person.yaml``       the facts about a person that rules may use
- ``parameters/<state>/<scheme>/<name>.yaml``  dated values (OpenFisca format)
- ``schemes/<state>/<scheme>.yaml``  conditions and benefit, each with a source
- ``tests/<state>/<scheme>.yaml``    test citizens with expected results

Every parameter value and every condition is dated, so the rulebook can answer
"what were the rules on a given day?" and history is never overwritten.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .safe_eval import RuleExpressionError, evaluate, names_used

ROOT = Path(__file__).resolve().parent.parent


def _to_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


@dataclass
class ParamValue:
    start: dt.date
    value: Any
    reference: dict[str, Any]


@dataclass
class Parameter:
    key: str
    description: str
    unit: str | None
    values: list[ParamValue]

    def at(self, on: dt.date) -> ParamValue | None:
        current = None
        for v in self.values:
            if v.start <= on:
                current = v
        return current


@dataclass
class Condition:
    id: str
    text: str
    when: str
    source: dict[str, Any]
    valid_from: dt.date
    valid_until: dt.date | None = None
    kind: str = "eligibility"

    def active(self, on: dt.date) -> bool:
        return self.valid_from <= on and (self.valid_until is None or on <= self.valid_until)


@dataclass
class Scheme:
    id: str
    data: dict[str, Any]
    conditions: list[Condition]
    params: dict[str, Parameter] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.data["name"]

    def params_at(self, on: dt.date) -> dict[str, Any]:
        out = {}
        for name, p in self.params.items():
            v = p.at(on)
            if v is not None:
                out[name] = v.value
        return out


class Rulebook:
    def __init__(self, root: Path | str = ROOT):
        self.root = Path(root)
        self.person_schema: dict[str, dict[str, Any]] = {}
        self.schemes: dict[str, Scheme] = {}
        self.sources: dict[str, dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        schema = yaml.safe_load((self.root / "schema" / "person.yaml").read_text(encoding="utf-8"))
        self.person_schema = schema["fields"]
        src_file = self.root / "sources" / "index.yaml"
        if src_file.exists():
            self.sources = yaml.safe_load(src_file.read_text(encoding="utf-8")) or {}
        for path in sorted((self.root / "schemes").rglob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            conditions = [
                Condition(
                    id=c["id"],
                    text=c["text"],
                    when=c["when"],
                    source=c.get("source", {}),
                    valid_from=_to_date(c["valid_from"]),
                    valid_until=_to_date(c["valid_until"]) if c.get("valid_until") else None,
                    kind=c.get("kind", "eligibility"),
                )
                for c in data.get("conditions", [])
            ]
            scheme = Scheme(id=data["id"], data=data, conditions=conditions)
            param_dir = self.root / "parameters" / Path(*data["id"].split("."))
            for ppath in sorted(param_dir.glob("*.yaml")):
                pdata = yaml.safe_load(ppath.read_text(encoding="utf-8"))
                values = []
                for start, entry in (pdata.get("values") or {}).items():
                    entry = entry if isinstance(entry, dict) else {"value": entry}
                    values.append(
                        ParamValue(
                            start=_to_date(start),
                            value=entry.get("value"),
                            reference=(entry.get("metadata") or {}).get("reference", {}),
                        )
                    )
                values.sort(key=lambda v: v.start)
                meta = pdata.get("metadata") or {}
                scheme.params[ppath.stem] = Parameter(
                    key=f"{data['id']}.{ppath.stem}",
                    description=pdata.get("description", ""),
                    unit=meta.get("unit"),
                    values=values,
                )
            self.schemes[scheme.id] = scheme

    # -------------------------------------------------------------- persons
    def normalise_person(self, person: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for name, spec in self.person_schema.items():
            value = person.get(name, spec.get("default"))
            if value is None:
                out[name] = None
                continue
            kind = spec.get("type")
            if kind == "int":
                value = int(value)
            elif kind == "number":
                value = float(value)
            elif kind == "bool":
                value = value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes"}
            elif kind == "enum" and value not in spec.get("values", []):
                raise ValueError(f"{name} must be one of {spec.get('values')}, got {value!r}")
            out[name] = value
        unknown = set(person) - set(self.person_schema)
        if unknown:
            raise ValueError(f"unknown person fields: {sorted(unknown)}")
        return out

    # ------------------------------------------------------------- evaluate
    def evaluate(self, person: dict[str, Any], on: dt.date | str | None = None,
                 schemes: list[str] | None = None) -> dict[str, Any]:
        on = _to_date(on) if on else dt.date.today()
        p = self.normalise_person(person)
        results = {}
        for sid, scheme in self.schemes.items():
            if schemes and sid not in schemes:
                continue
            launched = _to_date(scheme.data["launched"])
            closed = scheme.data.get("closed")
            if on < launched or (closed and on > _to_date(closed)):
                results[sid] = {"eligible": False, "in_force": False, "monthly_inr": 0, "reasons": []}
                continue
            params = scheme.params_at(on)
            reasons = []
            for c in scheme.conditions:
                if not c.active(on):
                    continue
                met = bool(evaluate(c.when, p, params))
                reasons.append({
                    "id": c.id,
                    "text": self.render_text(c.text, params),
                    "met": met,
                    "source": c.source,
                })
            eligible = all(r["met"] for r in reasons)
            monthly = 0
            benefit = scheme.data.get("benefit", {}).get("monthly_inr")
            if eligible and benefit:
                monthly = evaluate(benefit, p, params)
                if isinstance(monthly, float) and monthly.is_integer():
                    monthly = int(monthly)
            results[sid] = {"eligible": eligible, "in_force": True, "monthly_inr": monthly, "reasons": reasons}
        return results

    @staticmethod
    def render_text(text: str, params: dict[str, Any]) -> str:
        def fmt(v: Any) -> str:
            if isinstance(v, list):
                return ", ".join(str(x) for x in v)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 1000:
                return f"{v:,.0f}"
            return str(v)
        try:
            return text.format(**{k: fmt(v) for k, v in params.items()})
        except (KeyError, IndexError):
            return text

    # ----------------------------------------------------------- inspection
    def rules_at(self, scheme_id: str, on: dt.date | str | None = None) -> dict[str, Any]:
        on = _to_date(on) if on else dt.date.today()
        s = self.schemes[scheme_id]
        params = s.params_at(on)
        return {
            "id": s.id,
            "name": s.name,
            "as_of": on.isoformat(),
            "conditions": [
                {"id": c.id, "text": self.render_text(c.text, params), "when": c.when,
                 "source": c.source, "valid_from": c.valid_from.isoformat(),
                 "valid_until": c.valid_until.isoformat() if c.valid_until else None}
                for c in s.conditions if c.active(on)
            ],
            "parameters": {
                name: {"value": v.value, "since": v.start.isoformat(), "reference": v.reference,
                       "description": s.params[name].description, "unit": s.params[name].unit}
                for name in s.params if (v := s.params[name].at(on))
            },
        }

    def check(self) -> list[str]:
        """Structural validation. Returns a list of problems (empty means valid)."""
        problems = []
        for sid, s in self.schemes.items():
            for key in ("name", "launched", "department", "summary"):
                if key not in s.data:
                    problems.append(f"{sid}: missing '{key}'")
            ids = [c.id for c in s.conditions]
            for c in s.conditions:
                where = f"{sid}.{c.id}"
                for need in ("doc", "page", "quote"):
                    if not c.source.get(need):
                        problems.append(f"{where}: source is missing '{need}'")
                if c.source.get("doc") and c.source["doc"] not in self.sources:
                    problems.append(f"{where}: source doc '{c.source['doc']}' is not in sources/index.yaml")
                if c.valid_until and c.valid_until < c.valid_from:
                    problems.append(f"{where}: valid_until is before valid_from")
                try:
                    for root, attr in names_used(c.when):
                        if root == "person" and attr not in self.person_schema:
                            problems.append(f"{where}: unknown person field '{attr}'")
                        if root == "params" and attr not in s.params:
                            problems.append(f"{where}: unknown parameter '{attr}'")
                except RuleExpressionError as e:
                    problems.append(f"{where}: {e}")
            for cid in set(ids):
                periods = sorted((c.valid_from, c.valid_until or dt.date.max) for c in s.conditions if c.id == cid)
                for (a0, a1), (b0, _) in zip(periods, periods[1:]):
                    if b0 <= a1:
                        problems.append(f"{sid}.{cid}: overlapping validity periods")
            for name, p in s.params.items():
                if not p.values:
                    problems.append(f"{sid}: parameter '{name}' has no values")
                for v in p.values:
                    ref = v.reference or {}
                    if not ref.get("doc"):
                        problems.append(f"{sid}: parameter '{name}' value from {v.start} has no reference doc")
        return problems
