def test_stock_defaults_to_zero(client):
    """POST /products without stock creates the product with stock 0."""
    r = client.post("/products", json={"name": "Bow", "price_cents": 0})
    assert r.status_code == 201
    assert r.json()["stock"] == 0


def test_list_is_ordered_by_id(client, make_product):
    """GET /products lists products by id ascending, and ids increase in creation order."""
    a, b, c = make_product(), make_product(), make_product()
    assert a["id"] < b["id"] < c["id"]
    ids = [p["id"] for p in client.get("/products").json()]
    assert ids == sorted(ids)
