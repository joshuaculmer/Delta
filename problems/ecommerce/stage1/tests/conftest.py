import os
import uuid

import httpx
import pytest


@pytest.fixture
def client():
    with httpx.Client(base_url=os.environ["DELTA_BASE_URL"], timeout=10) as c:
        yield c


@pytest.fixture
def make_product(client):
    def make(**overrides):
        body = {"name": f"item-{uuid.uuid4().hex[:8]}", "price_cents": 450, "stock": 3, **overrides}
        r = client.post("/products", json=body)
        assert r.status_code == 201
        return r.json()

    return make
