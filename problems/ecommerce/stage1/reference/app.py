import os

from flask import Flask, jsonify, request

app = Flask(__name__)
products: dict[int, dict] = {}


def error(status, message):
    return jsonify({"error": message}), status


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.post("/products")
def create_product():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error(400, "body must be a JSON object")
    name, price, stock = body.get("name"), body.get("price_cents"), body.get("stock", 0)
    if not isinstance(name, str) or not name:
        return error(400, "name must be a non-empty string")
    if not is_int(price) or price < 0:
        return error(400, "price_cents must be a non-negative integer")
    if not is_int(stock) or stock < 0:
        return error(400, "stock must be a non-negative integer")
    product = {"id": len(products) + 1, "name": name, "price_cents": price, "stock": stock}
    products[product["id"]] = product
    return jsonify(product), 201


@app.get("/products")
def list_products():
    return jsonify([products[i] for i in sorted(products)])


@app.get("/products/<int:product_id>")
def get_product(product_id):
    if product_id not in products:
        return error(404, "product not found")
    return jsonify(products[product_id])


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ["PORT"]))
