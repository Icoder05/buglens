# Generated onboarding material

BugLens generated these from static analysis of each repository (at the earliest SWE-bench Lite test
commit). Diagrams are never drawn by an LLM; every summary sentence cites `file:line`.

| Repository | Guide | Architecture diagram |
| --- | --- | --- |
| pallets/flask | [guide.md](pallets__flask/guide.md) | [block.svg](pallets__flask/diagrams/block.svg) |
| psf/requests | [guide.md](psf__requests/guide.md) | [block.svg](psf__requests/diagrams/block.svg) |
| django/django | [guide.md](django__django/guide.md) | [block.svg](django__django/diagrams/block.svg) |

Each of these three folders also has `diagrams/packages/` (package drill-downs), `diagrams/classes/`
(class diagrams), `diagrams/callflow/` (call flows from entry points), `summaries.json` and
`diagrams/faithfulness.json` showing that 100% of diagram elements were verified.

The other nine folders contain only `summaries.json`: package summaries generated for all 12 test
repositories so that they could be tested as a ranking feature (system S6b, research question RQ4).
