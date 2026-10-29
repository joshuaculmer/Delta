import pytest


@pytest.mark.parametrize("body", [
    {"price_cents": 100},
    {"name": "", "price_cents": 100},
    {"name": "x", "price_cents": -1},
    {"name": "x", "price_cents": "100"},
    {"name": "x", "price_cents": True},
    {"name": "x", "price_cents": 100, "stock": -2},
])
def test_create_product_rejects_invalid_body(client, body):
    """POST /products with a missing, empty, mistyped, or negative field returns 400 with an error key."""
    r = client.post("/products", json=body)
    assert r.status_code == 400
    assert "error" in r.json()


def test_create_product_rejects_non_object(client):
    """POST /products with a JSON array body returns 400 with an error key."""
    r = client.post("/products", json=[1, 2])
    assert r.status_code == 400
    assert "error" in r.json()


def test_get_missing_product(client):
    """GET /products/{id} for an unknown id returns 404 with an error key."""
    r = client.get("/products/999999")
    assert r.status_code == 404
    assert "error" in r.json()
