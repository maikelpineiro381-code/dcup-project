from flask import Flask, request, jsonify, send_from_directory
import uuid
import time
import requests
import os

app = Flask(__name__)

# -------------------------------
# Estado en memoria
# -------------------------------
orderbook = {
    "buy": [],
    "sell": [],
    "collectible_buy": [],
    "collectible_sell": []
}
trades = []

# -------------------------------
# URLs dinámicas (se configuran en Render)
# -------------------------------
WALLET_URL = os.environ.get("WALLET_URL", "http://127.0.0.1:5001/tx/send")
COLLECTIBLE_URL = os.environ.get("COLLECTIBLE_URL", "http://127.0.0.1:5001")

# -------------------------------
# Ruta raíz
# -------------------------------
@app.route("/")
def home():
    return jsonify({
        "message": "Bienvenido al DCUP Exchange",
        "endpoints": ["/order", "/orderbook", "/trades", "/collectible/orderbook"]
    })

# -------------------------------
# Favicon
# -------------------------------
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

# -------------------------------
# Crear orden (tokens normales)
# -------------------------------
@app.route("/order", methods=["POST"])
def create_order():
    data = request.get_json() or {}
    user = data.get("user")
    order_type = data.get("type")  # "buy" o "sell"
    amount = int(data.get("amount", 0))
    price = float(data.get("price", 0))

    if order_type not in ["buy", "sell"]:
        return jsonify({"status": "error", "message": "Tipo de orden inválido"}), 400

    order = {
        "id": str(uuid.uuid4()),
        "user": user,
        "type": order_type,
        "amount": amount,
        "price": price,
        "timestamp": time.time()
    }

    orderbook[order_type].append(order)
    match_orders()
    return jsonify({"status": "success", "order": order}), 201

# -------------------------------
# Crear orden (coleccionables)
# -------------------------------
@app.route("/collectible/order", methods=["POST"])
def create_collectible_order():
    data = request.get_json() or {}
    user = data.get("user")
    order_type = data.get("type")  # "collectible_buy" o "collectible_sell"
    cid = data.get("id")
    price = float(data.get("price", 0))

    if order_type not in ["collectible_buy", "collectible_sell"]:
        return jsonify({"status": "error", "message": "Tipo de orden inválido"}), 400

    order = {
        "id": str(uuid.uuid4()),
        "user": user,
        "type": order_type,
        "collectible_id": cid,
        "price": price,
        "timestamp": time.time()
    }

    orderbook[order_type].append(order)
    match_collectible_orders()
    return jsonify({"status": "success", "order": order}), 201

# -------------------------------
# Ver libro de órdenes
# -------------------------------
@app.route("/orderbook", methods=["GET"])
def get_orderbook():
    return jsonify(orderbook), 200

@app.route("/collectible/orderbook", methods=["GET"])
def get_collectible_orderbook():
    return jsonify({
        "collectible_buy": orderbook["collectible_buy"],
        "collectible_sell": orderbook["collectible_sell"]
    }), 200

# -------------------------------
# Ver trades ejecutados
# -------------------------------
@app.route("/trades", methods=["GET"])
def get_trades():
    return jsonify(trades), 200

# -------------------------------
# Motor de emparejamiento (tokens)
# -------------------------------
def match_orders():
    global orderbook, trades

    for buy in list(orderbook["buy"]):
        for sell in list(orderbook["sell"]):
            if buy["price"] >= sell["price"] and buy["amount"] == sell["amount"]:
                trade = {
                    "buy_user": buy["user"],
                    "sell_user": sell["user"],
                    "amount": buy["amount"],
                    "price": sell["price"],
                    "timestamp": time.time(),
                    "type": "token"
                }
                trades.append(trade)

                try:
                    tx = {
                        "username": sell["user"],
                        "to": buy["user"],
                        "amount": buy["amount"]
                    }
                    r = requests.post(WALLET_URL, json=tx)
                    trade["blockchain_result"] = r.json()
                except Exception as e:
                    trade["blockchain_result"] = {"error": str(e)}

                orderbook["buy"].remove(buy)
                orderbook["sell"].remove(sell)
                break

# -------------------------------
# Motor de emparejamiento (coleccionables)
# -------------------------------
def match_collectible_orders():
    global orderbook, trades

    for buy in list(orderbook["collectible_buy"]):
        for sell in list(orderbook["collectible_sell"]):
            if buy["collectible_id"] == sell["collectible_id"] and buy["price"] >= sell["price"]:
                trade = {
                    "buy_user": buy["user"],
                    "sell_user": sell["user"],
                    "collectible_id": buy["collectible_id"],
                    "price": sell["price"],
                    "timestamp": time.time(),
                    "type": "collectible"
                }
                trades.append(trade)

                try:
                    payload = {
                        "from": sell["user"],
                        "to": buy["user"],
                        "id": buy["collectible_id"]
                    }
                    r = requests.post(f"{COLLECTIBLE_URL}/collectible/transfer", json=payload)
                    trade["blockchain_result"] = r.json()
                except Exception as e:
                    trade["blockchain_result"] = {"error": str(e)}

                orderbook["collectible_buy"].remove(buy)
                orderbook["collectible_sell"].remove(sell)
                break

# -------------------------------
# Arranque del servidor (Render)
# -------------------------------
if __name__ == "__main__":
    os.makedirs(os.path.join(app.root_path, 'static'), exist_ok=True)
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)
