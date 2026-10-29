def test_create_product(client):
    """POST /products returns 201 with the product, including a server-assigned id."""
    r = client.post("/products", json={"name": "Ribbon", "price_cents": 450, "stock": 12})
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "name", "price_cents", "stock"}
    assert body["name"] == "Ribbon"
    assert body["price_cents"] == 450
    assert body["stock"] == 12
    assert isinstance(body["id"], int) and body["id"] > 0


def test_get_product(client, make_product):
    """GET /products/{id} returns the product that was created."""
    created = make_product()
    r = client.get(f"/products/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_list_products(client, make_product):
    """GET /products includes created products."""
    a, b = make_product(), make_product()
    r = client.get("/products")
    assert r.status_code == 200
    assert a in r.json() and b in r.json()
