# Rulebook file format

How to write a scheme so the engine can apply it and people can audit it. The example below is a made-up scheme; its numbers are not real.

## 1. Register the source document: `sources/index.yaml`

```yaml
gr-202501011200000000:
  kind: government_resolution
  code: "202501011200000000"
  date: 2025-01-01
  department: Example Department, Government of Maharashtra
  title_mr: <title in Marathi as printed>
  title_en: <English title>
  url: https://gr.maharashtra.gov.in/Site/Upload/Government%20Resolutions/Marathi/202501011200000000.pdf
  local: sources/mh/202501011200000000.pdf
  language: mr
```

## 2. The scheme: `schemes/mh/<scheme_name>.yaml`

```yaml
id: mh.example_support            # mh.<snake_case_name>
name: Example Support Yojana       # official name in English letters
name_mr: <name in Marathi>
department: Example Department, Government of Maharashtra
summary: One plain-English sentence on who gets what.
launched: 2025-01-01               # date of the founding order
apply_url: https://example.gov.in/  # optional
benefit:
  monthly_inr: "params.monthly_amount"      # expression; may use person and params
  source: {doc: gr-202501011200000000, page: 2, clause: "3", quote: "<exact words>", quote_en: "<translation>"}
conditions:                        # every condition must be true to be eligible
  - id: resident
    text: Lives in Maharashtra     # plain English; {param_name} is replaced by the value
    when: "person.state == 'MH'"   # expression over person.<field> and params.<name>
    valid_from: 2025-01-01
    source: {doc: gr-202501011200000000, page: 2, clause: "4(1)", quote: "<exact words>", quote_en: "<translation>"}
  - id: age
    text: "Aged {age_min} to {age_max}"
    when: "params.age_min <= person.age <= params.age_max"
    valid_from: 2025-01-01
    source: {...}
  - id: no_tax_payer
    kind: disqualification         # optional label for rules that exclude people
    text: No one in the family pays income tax
    when: "not person.family_income_tax_payer"
    valid_from: 2025-01-01
    source: {...}
```

Expressions may use only `person.<field>` (fields listed in `schema/person.yaml`), `params.<name>`, comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, chained like `a <= x <= b`), `and`, `or`, `not`, `+ - * /`, lists `[...]`, and `min`, `max`, `abs`, `len`.

## 3. Parameters: `parameters/mh/<scheme_name>/<param_name>.yaml`

One file per changeable number or list. Values are dated; never edit or delete old values, add new dates.

```yaml
description: Maximum age in completed years
metadata:
  unit: year
values:
  2025-01-01:
    value: 60
    metadata:
      reference: {doc: gr-202501011200000000, page: 2, clause: "4(2)", quote: "<exact words>", quote_en: "<translation>"}
```

## 4. Tests: `tests/mh/<scheme_name>.yaml`

```yaml
scheme: mh.example_support
base: &base {age: 35, gender: female, state: MH, annual_family_income: 100000}
cases:
  - name: typical eligible person
    date: 2025-01-15
    person: {<<: *base}
    expect: {eligible: true, monthly_inr: 1000}
    source: GR 202501011200000000 p.2 clause 3
  - name: age 61 is not eligible
    date: 2025-01-15
    person: {<<: *base, age: 61}
    expect: {eligible: false}
    source: GR 202501011200000000 p.2 clause 4(2)
```

Write cases just below, at and just above every limit, one per condition, and one dated before the scheme starts (`expect: {eligible: false, in_force: false}`).

## 5. Check

```bash
python -m niyam_rulebook test    # must print 0 failed and no PROBLEM lines
```
