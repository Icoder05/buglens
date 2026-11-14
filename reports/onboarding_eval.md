# Onboarding evaluation

No claim is made about onboarding speed (no user study).

## FR-O1 Diagram faithfulness

Share of diagram nodes and edges re-derived from the static-analysis graphs.

| repo | diagrams | elements | verified_pct |
| --- | --- | --- | --- |
| pallets/flask | 32 | 395 | 100.0 |
| psf/requests | 27 | 355 | 100.0 |
| django/django | 31 | 1678 | 100.0 |

## FR-O2 Citation validity

Sentences kept/dropped by the strict citation validator.

| repo | packages | sentences | kept | dropped | kept_pct | valid_citation_pct | complete |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pallets/flask | 18 | 42 | 42 | 0 | 100.0 | 100.0 | True |
| psf/requests | 12 | 27 | 27 | 0 | 100.0 | 100.0 | True |
| django/django | 17 | 39 | 38 | 1 | 97.4 | 98.4 | True |

## FR-O3 Human rating of package summaries

Sheet: `reports/summary_ratings.csv` (fill `rating` with correct / partly / wrong, then rerun `buglens onboard-eval`). Single rater; the `note` column says who rated (Claude, pending the author's confirmation).

Rated 29/29: correct 86.2%, partly 13.8%, wrong 0.0%.

## FR-O4 Ask-the-codebase retrieval (QA file Acc@5)

Overall Acc@5: **0.933** (14/15).

| repo | acc@5 | questions |
| --- | --- | --- |
| pallets/flask | 1.0 | 8 |
| psf/requests | 0.857 | 7 |

| repo | question | hit@5 | top5 |
| --- | --- | --- | --- |
| pallets/flask | where are blueprints registered on the application? | 1 | src/flask/blueprints.py, src/flask/app.py, src/flask/debughelpers.py, src/flask/templating.py, src/flask/cli.py |
| pallets/flask | how is configuration loaded from a python file? | 1 | src/flask/config.py, src/flask/cli.py, src/flask/json/__init__.py, src/flask/app.py, src/flask/helpers.py |
| pallets/flask | where is the request context pushed and popped? | 1 | src/flask/ctx.py, src/flask/app.py, src/flask/testing.py, src/flask/helpers.py, src/flask/scaffold.py |
| pallets/flask | where is the session cookie signed and saved? | 1 | src/flask/sessions.py, src/flask/testing.py, src/flask/wrappers.py, src/flask/json/tag.py, src/flask/ctx.py |
| pallets/flask | where are jinja templates rendered? | 1 | src/flask/templating.py, src/flask/app.py, src/flask/scaffold.py, src/flask/json/__init__.py, src/flask/helpers.py |
| pallets/flask | where is the flask run command line implemented? | 1 | src/flask/cli.py, src/flask/debughelpers.py, src/flask/app.py, examples/tutorial/flaskr/db.py, src/flask/__main__.py |
| pallets/flask | how are non-standard types like tuples and UUIDs tagged when serialising the session to JSON? | 1 | src/flask/json/tag.py, src/flask/sessions.py, src/flask/json/__init__.py, src/flask/testing.py, src/flask/scaffold.py |
| pallets/flask | where do class-based views dispatch to the method handler? | 1 | src/flask/views.py, src/flask/app.py, examples/javascript/js_example/views.py, examples/javascript/js_example/__init__.py, src/flask/wrappers.py |
| psf/requests | where is HTTP basic authentication implemented? | 1 | requests/auth.py, requests/packages/oauthlib/common.py, requests/packages/urllib3/util.py, requests/packages/oauthlib/oauth1/rfc5849/__init__.py, requests/packages/oauthlib/oauth2/draft25/__init__.py |
| psf/requests | where is a prepared request sent and redirects followed? | 1 | requests/models.py, requests/exceptions.py, requests/sessions.py, requests/api.py, requests/defaults.py |
| psf/requests | where are cookies stored in a cookie jar? | 1 | requests/cookies.py, requests/utils.py, requests/sessions.py, requests/models.py |
| psf/requests | where is the case-insensitive dictionary used for headers? | 1 | requests/structures.py, requests/utils.py, requests/packages/urllib3/packages/ordered_dict.py, requests/models.py, requests/packages/oauthlib/oauth1/rfc5849/parameters.py |
| psf/requests | where are the get and post convenience functions defined? | 0 | requests/__init__.py, requests/structures.py, requests/models.py, requests/hooks.py, requests/utils.py |
| psf/requests | where are request hooks dispatched? | 1 | requests/hooks.py, requests/models.py, requests/auth.py, requests/sessions.py, requests/cookies.py |
| psf/requests | where are the library's exception classes defined? | 1 | requests/packages/urllib3/exceptions.py, requests/exceptions.py, requests/packages/oauthlib/oauth1/__init__.py, requests/packages/oauthlib/oauth2/__init__.py, requests/packages/oauthlib/oauth2/draft25/__init__.py |
