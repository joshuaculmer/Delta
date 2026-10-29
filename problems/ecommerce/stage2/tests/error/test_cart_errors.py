import pytest


@pytest.mark.parametrize("body", [
    {"quantity": 1},
    {"product_id": 1},
    {"product_id": 1, "quantity": 0},
    {"product_id": 1, "quantity": "2"},
    {"product_id": 1, "quantity": True},
])
def test_add_item_rejects_invalid_body(client, make_cart, body):
    """POST /carts/{id}/items with a missing, mistyped, or non-positive field returns 400 with an error key."""
    r = client.post(f"/carts/{make_cart()['id']}/items", json=body)
    assert r.status_code == 400
    assert "error" in r.json()


def test_get_missing_cart(client):
    """GET /carts/{id} for an unknown id returns 404 with an error key."""
    r = client.get("/carts/999999")
    assert r.status_code == 404
    assert "error" in r.json()


def test_add_unknown_product(client, make_cart):
    """POST /carts/{id}/items with an unknown product returns 404 with an error key."""
    r = client.post(f"/carts/{make_cart()['id']}/items", json={"product_id": 999999, "quantity": 1})
    assert r.status_code == 404
    assert "error" in r.json()


def test_add_beyond_stock(client, make_product, make_cart):
    """POST /carts/{id}/items beyond the product's stock returns 409 and leaves the cart unchanged."""
    product, cart = make_product(stock=2), make_cart()
    client.post(f"/carts/{cart['id']}/items", json={"product_id": product["id"], "quantity": 2})
    r = client.post(f"/carts/{cart['id']}/items", json={"product_id": product["id"], "quantity": 1})
    assert r.status_code == 409
    assert "error" in r.json()
    assert client.get(f"/carts/{cart['id']}").json()["items"][0]["quantity"] == 2


def test_remove_item_not_in_cart(client, make_product, make_cart):
    """DELETE /carts/{id}/items/{product_id} for a product not in the cart returns 404 with an error key."""
    r = client.delete(f"/carts/{make_cart()['id']}/items/{make_product()['id']}")
    assert r.status_code == 404
    assert "error" in r.json()
