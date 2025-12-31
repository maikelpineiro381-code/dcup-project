import os
import json
import hashlib
import secrets
import requests
import time
from typing import Dict, Any
from ecdsa import SigningKey, SECP256k1
from flask import Flask, request, jsonify

# -------------------------------
# Configuración
# -------------------------------
DATA_DIR = "."
USERS_FILE = os.path.join(DATA_DIR, "users.json")
COLLECTIBLES_FILE = os.path.join(DATA_DIR, "collectibles.json")
CORE_URL = os.environ.get("CORE_URL", "http://127.0.0.1:5000")  # Se ajusta en Render

WORDLIST = [
    "cactus","river","moon","light","echo","stone","forest","rapid","silver","delta","vapor","matrix",
    "ember","tropic","saffron","quartz","lumen","fenix","aurora","bridge","pixel","drift","nova",
    "liber","origin","vault","chain","genesis","crypto"
]

def generate_mnemonic(n: int = 12) -> str:
    return " ".join(secrets.choice(WORDLIST) for _ in range(n))

def load_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path: str, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def address_from_pubkey_bytes(pubkey_bytes: bytes) -> str:
    return hashlib.sha256(pubkey_bytes).hexdigest()

# -------------------------------
# Clase Wallet
# -------------------------------
class Wallet:
    def __init__(self, mnemonic: str = None):
        self.mnemonic = mnemonic or generate_mnemonic(12)
        seed = hashlib.sha256(self.mnemonic.encode()).digest()
        self.private_key = SigningKey.from_string(seed, curve=SECP256k1)
        self.public_key = self.private_key.get_verifying_key()
        self.address = address_from_pubkey_bytes(self.public_key.to_string())

    def sign(self, from_addr: str, to_addr: str, amount: int) -> str:
        message = f"{from_addr}{to_addr}{amount}"
        return self.private_key.sign(message.encode()).hex()

    def export(self) -> Dict[str, str]:
        return {
            "mnemonic": self.mnemonic,
            "address": self.address,
            "private_key": self.private_key.to_string().hex(),
            "public_key": self.public_key.to_string().hex()
        }

# -------------------------------
# Estado
# -------------------------------
users: Dict[str, Dict[str, Any]] = load_json(USERS_FILE, {})
collectibles: Dict[str, Dict[str, Any]] = load_json(COLLECTIBLES_FILE, {})

def ensure_username_available(username: str) -> bool:
    return username not in users

def get_wallet_by_username(username: str) -> Wallet:
    data = users.get(username)
    if not data or "mnemonic" not in data:
        return None
    w = Wallet(mnemonic=data["mnemonic"])
    w.address = data.get("address", w.address)
    return w

# -------------------------------
# Servidor Flask
# -------------------------------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return f"""
    <h1>Wallet Server</h1>
    <p>CORE_URL actual: {CORE_URL}</p>
    """

@app.route("/users", methods=["GET"])
def list_users():
    summary = {u: {"address": users[u]["address"], "public_key": users[u]["public_key"]} for u in users}
    return jsonify(summary), 200

@app.route("/user/create", methods=["POST"])
def create_user():
    data = request.get_json() or {}
    username = data.get("username")
    if not username or not isinstance(username, str):
        return jsonify({"status": "error", "message": "username requerido"}), 400
    if not ensure_username_available(username):
        return jsonify({"status": "error", "message": "username ya existe"}), 400

    wallet = Wallet()
    users[username] = wallet.export()
    save_json(USERS_FILE, users)

    return jsonify({
        "status": "success",
        "username": username,
        "mnemonic": wallet.mnemonic,
        "address": wallet.address,
        "public_key": wallet.public_key.to_string().hex()
    }), 201

@app.route("/user/<username>", methods=["GET"])
def get_user(username: str):
    w = get_wallet_by_username(username)
    if not w:
        return jsonify({"status": "error", "message": "usuario no encontrado"}), 404
    return jsonify({
        "status": "success",
        "username": username,
        "address": w.address,
        "public_key": w.public_key.to_string().hex()
    }), 200

@app.route("/tx/send", methods=["POST"])
def send_tx():
    data = request.get_json() or {}
    username = data.get("username")
    to_addr = data.get("to")
    amount = data.get("amount")

    if not username or not to_addr:
        return jsonify({"status": "error", "message": "Campos requeridos"}), 400
    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError()
    except Exception:
        return jsonify({"status": "error", "message": "amount inválido"}), 400

    w = get_wallet_by_username(username)
    if not w:
        return jsonify({"status": "error", "message": "usuario no encontrado"}), 404

    signature = w.sign(w.address, to_addr, amount)
    tx = {
        "from": w.address,
        "to": to_addr,
        "amount": amount,
        "pubkey": w.public_key.to_string().hex(),
        "signature": signature
    }

    try:
        r = requests.post(f"{CORE_URL}/transaction", json=tx, timeout=10)
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error conectando al core: {str(e)}"}), 502

# -------------------------------
# Arranque del servidor Flask (Render)
# -------------------------------
if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        save_json(USERS_FILE, {})
    if not os.path.exists(COLLECTIBLES_FILE):
        save_json(COLLECTIBLES_FILE, {})

    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
