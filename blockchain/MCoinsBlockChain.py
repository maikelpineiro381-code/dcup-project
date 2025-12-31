# MCoinsBlockChain.py
import hashlib
import json
import time
import os
import secrets
from typing import Dict, Any, List, Tuple
from ecdsa import SigningKey, SECP256k1, VerifyingKey, BadSignatureError
from flask import Flask, request, jsonify

# -------------------------------
# Configuración y persistencia
# -------------------------------
DATA_DIR = "."
FOUNDER_WALLET_FILE = os.path.join(DATA_DIR, "GenWallet_wallet.json")
CHAIN_FILE = os.path.join(DATA_DIR, "DCUP_chain.json")
BALANCES_FILE = os.path.join(DATA_DIR, "DCUP_balances.json")
COLLECTIBLES_FILE = os.path.join(DATA_DIR, "DCUP_collectibles.json")
SUPPLY_TOTAL = 100_000_000

# -------------------------------
# Lista de palabras para mnemónica
# -------------------------------
WORDLIST = [
    "cactus","river","moon","light","echo","stone","forest","rapid","silver","delta","vapor","matrix",
    "ember","tropic","saffron","quartz","lumen","fenix","aurora","bridge","pixel","drift","nova",
    "liber","origin","vault","chain","genesis","crypto"
]

def generate_mnemonic(n: int = 12) -> str:
    return " ".join(secrets.choice(WORDLIST) for _ in range(n))

# -------------------------------
# Clase Wallet
# -------------------------------
class Wallet:
    def __init__(self, mnemonic: str = None):
        self.mnemonic = mnemonic or generate_mnemonic(12)
        seed = hashlib.sha256(self.mnemonic.encode()).digest()
        self.private_key = SigningKey.from_string(seed, curve=SECP256k1)
        self.public_key = self.private_key.get_verifying_key()
        self.address = hashlib.sha256(self.public_key.to_string()).hexdigest()

    def sign(self, from_addr: str, to_addr: str, amount: int) -> str:
        message = f"{from_addr}{to_addr}{amount}"
        return self.private_key.sign(message.encode()).hex()

    def export(self) -> Dict[str, str]:
        return {
            "name": "GenWallet",
            "mnemonic": self.mnemonic,
            "address": self.address,
            "private_key": self.private_key.to_string().hex(),
            "public_key": self.public_key.to_string().hex()
        }

# -------------------------------
# Utilidades
# -------------------------------
def is_hex(s: str) -> bool:
    try:
        bytes.fromhex(s)
        return True
    except Exception:
        return False

def address_from_pubkey_hex(pubkey_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(pubkey_hex)).hexdigest()

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

# -------------------------------
# Clase Blockchain
# -------------------------------
class Blockchain:
    def __init__(self):
        self.chain: List[Dict[str, Any]] = load_json(CHAIN_FILE, [])
        self.balances: Dict[str, int] = load_json(BALANCES_FILE, {})
        self.collectibles: Dict[str, Dict[str, Any]] = load_json(COLLECTIBLES_FILE, {})

    def _persist(self):
        save_json(CHAIN_FILE, self.chain)
        save_json(BALANCES_FILE, self.balances)
        save_json(COLLECTIBLES_FILE, self.collectibles)

    def verify_transaction(self, tx: Dict[str, Any]) -> Tuple[bool, str]:
        tx_type = tx.get("type", "token")

        # Validación de tokens (no génesis)
        if tx_type == "token" and tx['from'] != "GENESIS":
            # Campos mínimos
            if not isinstance(tx.get('from'), str) or not isinstance(tx.get('to'), str):
                return False, "Campos 'from' y 'to' deben ser strings"
            if not isinstance(tx.get('amount'), int) or tx['amount'] <= 0:
                return False, "El campo 'amount' debe ser un entero positivo"
            if not isinstance(tx.get('pubkey'), str) or not is_hex(tx['pubkey']):
                return False, "El campo 'pubkey' debe ser un hex válido"
            if not isinstance(tx.get('signature'), str) or not is_hex(tx['signature']):
                return False, "El campo 'signature' debe ser un hex válido"

            # Dirección derivada de pubkey
            derived_from = address_from_pubkey_hex(tx['pubkey'])
            if derived_from != tx['from']:
                return False, "La dirección 'from' no corresponde a la clave pública 'pubkey'"

            # Saldo
            if self.balances.get(tx['from'], 0) < tx['amount']:
                return False, "Saldo insuficiente"

            # Firma
            try:
                pubkey_bytes = bytes.fromhex(tx['pubkey'])
                vk = VerifyingKey.from_string(pubkey_bytes, curve=SECP256k1)
                message = f"{tx['from']}{tx['to']}{tx['amount']}"
                vk.verify(bytes.fromhex(tx['signature']), message.encode())
            except BadSignatureError:
                return False, "Firma inválida"
            except Exception as e:
                return False, f"Error verificando firma: {str(e)}"

        # Validación de coleccionables
        if tx_type == "collectible_create":
            if not tx.get("id") or tx["id"] in self.collectibles:
                return False, "ID inválido o ya existe"
            if not tx.get("to"):
                return False, "Propietario requerido"

        if tx_type == "collectible_transfer":
            cid = tx.get("id")
            if not cid or cid not in self.collectibles:
                return False, "Coleccionable no existe"
            if self.collectibles[cid]["owner"] != tx.get("from"):
                return False, "No eres el dueño"

        return True, "OK"

    def add_block(self, transactions: List[Dict[str, Any]]) -> str:
        # Validar todas las transacciones
        for tx in transactions:
            ok, msg = self.verify_transaction(tx)
            if not ok:
                raise ValueError(msg)

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time.time(),
            'transactions': transactions,
            'prev_hash': self.chain[-1]['hash'] if self.chain else "0"
        }
        block_string = json.dumps(block, sort_keys=True).encode()
        block['hash'] = hashlib.sha256(block_string).hexdigest()

        # Aplicar efectos de estado
        for tx in transactions:
            tx_type = tx.get("type", "token")

            if tx_type == "token":
                if tx['from'] != "GENESIS":
                    self.balances[tx['from']] = self.balances.get(tx['from'], 0) - tx['amount']
                self.balances[tx['to']] = self.balances.get(tx['to'], 0) + tx['amount']

            elif tx_type == "collectible_create":
                cid = tx["id"]
                self.collectibles[cid] = {
                    "id": cid,
                    "name": tx.get("name"),
                    "owner": tx["to"],
                    "metadata": tx.get("metadata", {}),
                    "timestamp": time.time()
                }

            elif tx_type == "collectible_transfer":
                cid = tx["id"]
                self.collectibles[cid]["owner"] = tx["to"]
                self.collectibles[cid]["timestamp"] = time.time()

        self.chain.append(block)
        self._persist()
        return block['hash']

    def export_chain(self) -> List[Dict[str, Any]]:
        return self.chain

# -------------------------------
# Inicialización del fundador y génesis
# -------------------------------
def ensure_founder_and_genesis(chain: Blockchain):
    # Asegurar wallet del fundador
    if not os.path.exists(FOUNDER_WALLET_FILE):
        fundador = Wallet()
        save_json(FOUNDER_WALLET_FILE, fundador.export())
        print(f"Wallet del fundador (GenWallet) creada: {fundador.address}")
        print(f"Frase mnemónica: {fundador.mnemonic}")
    else:
        fundador_data = load_json(FOUNDER_WALLET_FILE, None)
        if not fundador_data or 'mnemonic' not in fundador_data or 'address' not in fundador_data:
            fundador = Wallet()
            save_json(FOUNDER_WALLET_FILE, fundador.export())
            print(f"Wallet del fundador (GenWallet) reparada: {fundador.address}")
            print(f"Frase mnemónica: {fundador.mnemonic}")
        else:
            fundador = Wallet(mnemonic=fundador_data['mnemonic'])
            fundador.address = fundador_data['address']

    # Crear génesis si la cadena está vacía
    if len(chain.chain) == 0:
        genesis_tx = {
            'type': 'token',
            'from': "GENESIS",
            'to': fundador.address,
            'amount': SUPPLY_TOTAL,
            'pubkey': fundador.public_key.to_string().hex(),
            'signature': "GENESIS"
        }
        chain.add_block([genesis_tx])
        chain.balances[fundador.address] = SUPPLY_TOTAL
        chain._persist()
        print("Bloque génesis creado y suministro inicial asignado.")

# -------------------------------
# Servidor Flask
# -------------------------------
app = Flask(__name__)
chain = Blockchain()
ensure_founder_and_genesis(chain)

@app.route("/", methods=['GET'])
def home():
    return """
    <h1>DCUP Blockchain Core</h1>
    <ul>
        <li><a href="/chain">/chain</a> → Ver la blockchain</li>
        <li><a href="/balance">/balance</a> → Ver balances</li>
        <li><a href="/collectibles">/collectibles</a> → Ver coleccionables</li>
        <li>/transaction (POST) → Enviar transacciones (token o coleccionable)</li>
        <li>/fund (POST) → Enviar fondos desde GenWallet</li>
    </ul>
    """

@app.route("/chain", methods=['GET'])
def get_chain():
    return jsonify(chain.export_chain()), 200

@app.route("/balance", methods=['GET'])
def get_balance():
    return jsonify(chain.balances), 200

@app.route("/collectibles", methods=['GET'])
def get_collectibles():
    return jsonify(chain.collectibles), 200

@app.route("/transaction", methods=['POST'])
def new_transaction():
    data = request.get_json() or {}
    tx_type = data.get("type", "token")

    try:
        if tx_type == "token":
            required = ['from', 'to', 'amount', 'pubkey', 'signature']
            missing = [k for k in required if k not in data]
            if missing:
                return jsonify({"status": "error", "message": f"Faltan campos: {', '.join(missing)}"}), 400

            tx = {
                'type': 'token',
                'from': data['from'],
                'to': data['to'],
                'amount': int(data['amount']),
                'pubkey': data['pubkey'],
                'signature': data['signature']
            }
            block_hash = chain.add_block([tx])

        elif tx_type == "collectible_create":
            required = ['id', 'to', 'name']
            missing = [k for k in required if k not in data]
            if missing:
                return jsonify({"status": "error", "message": f"Faltan campos: {', '.join(missing)}"}), 400

            tx = {
                'type': 'collectible_create',
                'id': data['id'],
                'to': data['to'],
                'name': data['name'],
                'metadata': data.get('metadata', {})
            }
            block_hash = chain.add_block([tx])

        elif tx_type == "collectible_transfer":
            required = ['id', 'from', 'to']
            missing = [k for k in required if k not in data]
            if missing:
                return jsonify({"status": "error", "message": f"Faltan campos: {', '.join(missing)}"}), 400

            tx = {
                'type': 'collectible_transfer',
                'id': data['id'],
                'from': data['from'],
                'to': data['to']
            }
            block_hash = chain.add_block([tx])

        else:
            return jsonify({"status": "error", "message": "Tipo de transacción desconocido"}), 400

        return jsonify({
            "status": "success",
            "hash": block_hash,
            "balances": chain.balances,
            "collectibles": chain.collectibles
        }), 201

    except ValueError as ve:
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error inesperado: {str(e)}"}), 400

@app.route('/fund', methods=['POST'])
def fund_user():
    data = request.get_json() or {}
    to_addr = data.get("to")
    amount = data.get("amount")

    if not isinstance(to_addr, str) or not to_addr:
        return jsonify({"status": "error", "message": "Campo 'to' requerido (string)"}), 400
    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError()
    except Exception:
        return jsonify({"status": "error", "message": "Campo 'amount' debe ser entero positivo"}), 400

    fundador_data = load_json(FOUNDER_WALLET_FILE, None)
    if not fundador_data or 'mnemonic' not in fundador_data or 'address' not in fundador_data:
        return jsonify({"status": "error", "message": "Wallet del fundador no disponible"}), 500

    fundador = Wallet(mnemonic=fundador_data["mnemonic"])
    fundador.address = fundador_data["address"]

    signature = fundador.sign(fundador.address, to_addr, amount)
    tx = {
        "type": "token",
        "from": fundador.address,
        "to": to_addr,
        "amount": amount,
        "pubkey": fundador.public_key.to_string().hex(),
        "signature": signature
    }

    try:
        block_hash = chain.add_block([tx])
        return jsonify({
            "status": "success",
            "hash": block_hash,
            "balances": chain.balances
        }), 201
    except ValueError as ve:
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error inesperado: {str(e)}"}), 400

# -------------------------------
# Arranque del servidor Flask
# -------------------------------
if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    # Asegurar archivos base
    if not os.path.exists(CHAIN_FILE):
        save_json(CHAIN_FILE, [])
    if not os.path.exists(BALANCES_FILE):
        save_json(BALANCES_FILE, {})
    if not os.path.exists(COLLECTIBLES_FILE):
        save_json(COLLECTIBLES_FILE, {})
    app.run(host="0.0.0.0", port=5000, debug=True)
