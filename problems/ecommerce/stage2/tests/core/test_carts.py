def test_create_cart(client):
    """POST /carts returns 201 with an empty cart."""
    r = client.post("/carts")
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "items", "total_cents"}
    assert body["items"] == [] and body["total_cents"] == 0
    assert isinstance(body["id"], int) and body["id"] > 0


def test_add_item(client, make_product, make_cart):
    """POST /carts/{id}/items adds the product and returns the cart with line and cart totals."""
    product, cart = make_product(price_cents=450, stock=5), make_cart()
    r = client.post(f"/carts/{cart['id']}/items", json={"product_id": product["id"], "quantity": 2})
    assert r.status_code == 200
    assert r.json() == {
        "id": cart["id"],
        "items": [{"product_id": product["id"], "quantity": 2, "unit_price_cents": 450, "line_total_cents": 900}],
        "total_cents": 900,
    }


def test_get_cart(client, make_product, make_cart):
    """GET /carts/{id} returns the cart with its items."""
    product, cart = make_product(), make_cart()
    added = client.post(f"/carts/{cart['id']}/items", json={"product_id": product["id"], "quantity": 1}).json()
    r = client.get(f"/carts/{cart['id']}")
    assert r.status_code == 200
    assert r.json() == added


def test_remove_item(client, make_product, make_cart):
    """DELETE /carts/{id}/items/{product_id} removes the product and returns the updated cart."""
    product, cart = make_product(), make_cart()
    client.post(f"/carts/{cart['id']}/items", json={"product_id": product["id"], "quantity": 1})
    r = client.delete(f"/carts/{cart['id']}/items/{product['id']}")
    assert r.status_code == 200
    assert r.json() == {"id": cart["id"], "items": [], "total_cents": 0}
