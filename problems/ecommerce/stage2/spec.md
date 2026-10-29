# Shopping Carts

Extend the existing product catalog API with shopping carts. All existing endpoints keep their current behavior.

## Cart

```json
{
  "id": 1,
  "items": [
    {"product_id": 3, "quantity": 2, "unit_price_cents": 450, "line_total_cents": 900}
  ],
  "total_cents": 900
}
```

- `id`: positive integer assigned by the server, increasing in creation order.
- `items`: ordered by `product_id` ascending. A product appears at most once.
- `unit_price_cents`: the product's current `price_cents`.
- `line_total_cents`: `quantity * unit_price_cents`.
- `total_cents`: sum of all `line_total_cents`. 0 for an empty cart.

## Endpoints

### POST /carts

- 201 with a new empty cart.

### GET /carts/{id}

- 200 with the cart.
- 404 with `{"error": "<message>"}` when no cart has that id.

### POST /carts/{id}/items

Body: `{"product_id": ..., "quantity": ...}`

- Adds `quantity` of the product to the cart. Adding a product already in the cart increases its quantity.
- 200 with the updated cart.
- 400 with `{"error": "<message>"}` when the body is not a JSON object, a field is missing, or a field is not an integer. `quantity` must be 1 or greater. Booleans are not integers.
- 404 with `{"error": "<message>"}` when the cart or the product does not exist.
- 409 with `{"error": "<message>"}` when the cart's resulting quantity for that product would exceed the product's `stock`. The cart is unchanged.

### DELETE /carts/{id}/items/{product_id}

- Removes the product from the cart.
- 200 with the updated cart.
- 404 with `{"error": "<message>"}` when the cart does not exist or the product is not in it.

## Normalization

- Responses contain exactly the fields shown. No extra fields.
- Error message text is free-form. Only the `error` key is checked.
