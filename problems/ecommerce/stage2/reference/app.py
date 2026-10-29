import os

from flask import Flask, jsonify, request

app = Flask(__name__)
products: dict[int, dict] = {}
carts: dict[int, dict[int, int]] = {}


def error(status, message):
    return jsonify({"error": message}), status


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def render_cart(cart_id):
    items = []
    for product_id in sorted(carts[cart_id]):
        quantity = carts[cart_id][product_id]
        price = products[product_id]["price_cents"]
        items.append({
            "product_id": product_id,
            "quantity": quantity,
            "unit_price_cents": price,
            "line_total_cents": quantity * price,
        })
    return {"id": cart_id, "items": items, "total_cents": sum(i["line_total_cents"] for i in items)}


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


@app.post("/carts")
def create_cart():
    cart_id = len(carts) + 1
    carts[cart_id] = {}
    return jsonify(render_cart(cart_id)), 201


@app.get("/carts/<int:cart_id>")
def get_cart(cart_id):
    if cart_id not in carts:
        return error(404, "cart not found")
    return jsonify(render_cart(cart_id))


@app.post("/carts/<int:cart_id>/items")
def add_item(cart_id):
    if cart_id not in carts:
        return error(404, "cart not found")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error(400, "body must be a JSON object")
    product_id, quantity = body.get("product_id"), body.get("quantity")
    if not is_int(product_id):
        return error(400, "product_id must be an integer")
    if not is_int(quantity) or quantity < 1:
        return error(400, "quantity must be a positive integer")
    if product_id not in products:
        return error(404, "product not found")
    new_quantity = carts[cart_id].get(product_id, 0) + quantity
    if new_quantity > products[product_id]["stock"]:
        return error(409, "not enough stock")
    carts[cart_id][product_id] = new_quantity
    return jsonify(render_cart(cart_id))


@app.delete("/carts/<int:cart_id>/items/<int:product_id>")
def remove_item(cart_id, product_id):
    if cart_id not in carts or product_id not in carts[cart_id]:
        return error(404, "item not found")
    del carts[cart_id][product_id]
    return jsonify(render_cart(cart_id))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ["PORT"]))
