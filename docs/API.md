# API documentation

| Document | Covers |
|---|---|
| **[API_BACKEND.md](API_BACKEND.md)** | Every HTTP endpoint of the Flask app: purpose, minimum role, path/query parameters, request body fields, example request, **real example response**, errors. Plus conventions (auth, CSRF, errors) and a curl quick start. |
| **[openapi.json](openapi.json)** | The same as an OpenAPI 3.0 file. Import it into Swagger UI, Postman or Insomnia to browse and try the API. |
| **[API_FRONTEND.md](API_FRONTEND.md)** | The Vue app's internal API: the HTTP client (`api.js`), session and roles (`session.js`), helpers (`utils.js`), the settings composable, every component's props/events/slots, the routes, and **which endpoint each screen calls from which function**. |

All three are generated from the code by `python3 scripts/gen_api_docs.py` (`make api-docs`):
example responses are captured by calling the real endpoints on a throw-away database.
`make test` fails if an endpoint is undocumented, a handler reads a field the docs don't list,
or a screen calls an endpoint that doesn't exist.
