# Niyam rulebook

Welfare scheme eligibility rules for Maharashtra, written as tested code.
Every rule links to the clause of the government order it comes from, and
every change is made by the [Niyam agent](https://github.com/usv240/niyam)
with its full reasoning saved as an [Entire](https://entire.io) checkpoint.

| Folder | What it holds |
|---|---|
| `schemes/` | Conditions and benefits of each scheme, each with a source quote |
| `parameters/` | Limits such as ages and income ceilings, with dated values |
| `tests/` | Test citizens with expected results, each citing its clause |
| `sources/` | The official government orders (PDF) |
| `glossary/` | How recurring legal phrases are interpreted |

## Use it

```bash
pip install -e .
python -m niyam_rulebook test                     # run every test citizen
python -m niyam_rulebook rules mh.ladki_bahin --date 2024-06-30
python -m niyam_rulebook simulate '{"age": 34, "gender": "female", "annual_family_income": 240000}' --date 2024-07-01
```

Information only. Final eligibility is always decided by the government department.
