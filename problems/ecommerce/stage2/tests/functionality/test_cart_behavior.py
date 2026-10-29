def test_adding_same_product_merges_quantity(client, make_product, make_cart):
    """Adding a product already in the cart increases its quantity instead of adding a second line."""
    product, cart = make_product(price_cents=100, stock=10), make_cart()
    client.post(f"/carts/{cart['id']}/items", json={"product_id": product["id"], "quantity": 2})
    r = client.post(f"/carts/{cart['id']}/items", json={"product_id": product["id"], "quantity": 3})
    assert r.json()["items"] == [{"product_id": product["id"], "quantity": 5, "unit_price_cents": 100, "line_total_cents": 500}]
    assert r.json()["total_cents"] == 500


def test_items_ordered_and_totaled(client, make_product, make_cart):
    """Cart items are ordered by product_id ascending and total_cents sums every line."""
    first, second = make_product(price_cents=250, stock=5), make_product(price_cents=100, stock=5)
    cart = make_cart()
    client.post(f"/carts/{cart['id']}/items", json={"product_id": second["id"], "quantity": 3})
    r = client.post(f"/carts/{cart['id']}/items", json={"product_id": first["id"], "quantity": 1})
    body = r.json()
    assert [i["product_id"] for i in body["items"]] == [first["id"], second["id"]]
    assert body["total_cents"] == 250 + 300
