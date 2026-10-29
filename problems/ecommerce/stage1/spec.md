# Product Catalog API

Build an HTTP JSON API for a store's product catalog.

## Running

- Provide an executable `run.sh` at the workspace root.
- `run.sh` starts the server listening on `127.0.0.1` at the port given by the `PORT` environment variable.
- `GET /health` returns status 200 once the server is ready.
- Data may live in memory. It does not need to survive a restart.

## Available Python packages

fastapi, uvicorn, flask, sqlalchemy, pydantic, httpx, requests, pytest. No other packages can be installed.

## Product

```json
{"id": 1, "name": "Ribbon", "price_cents": 450, "stock": 12}
```

- `id`: positive integer assigned by the server, increasing in creation order.
- `name`: non-empty string.
- `price_cents`: integer, 0 or greater.
- `stock`: integer, 0 or greater. Defaults to 0 when omitted.

## Endpoints

### POST /products

Body: `{"name": ..., "price_cents": ..., "stock": ...}`

- 201 with the created product.
- 400 with `{"error": "<message>"}` when the body is not a JSON object, a required field is missing, or a field has the wrong type or an out-of-range value. Booleans are not integers.

### GET /products

- 200 with a JSON array of all products, ordered by `id` ascending.

### GET /products/{id}

- 200 with the product.
- 404 with `{"error": "<message>"}` when no product has that id.

## Normalization

- Responses contain exactly the fields shown. No extra fields.
- Error message text is free-form. Only the `error` key is checked.
