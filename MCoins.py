import hashlib
import json
import time
import os
from ecdsa import SigningKey, SECP256k1, VerifyingKey
from flask import Flask, request, jsonify

# -------------------------------
# Clase Wallet
# -------------------------------
class Wallet:
    def __init__(self):
        self.private_key = SigningKey.generate(curve=SECP256k1)
        self.public_key = self.private_key.get_verifying_key()
        self.address = hashlib.sha256(self.public_key.to_string()).hexdigest()

    def sign(self, message: str):
        return self.private_key.sign(message.encode()).hex()

# -------------------------------
# Clase Blockchain
# -------------------------------
class Blockchain:
    def __init__(self, founder_wallet, supply_total):
        self.chain = []
        self.balances = {founder_wallet.address: supply_total}
        self.add_block([{
            'from': "GENESIS",
            'to': founder_wallet.address,
            'amount': supply_total,
            'pubkey': founder_wallet.public_key.to_string().hex(),
            'signature': "GENESIS"
        }])

    def add_block(self, transactions):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time.time(),
            'transactions': transactions,
            'prev_hash': self.chain[-1]['hash'] if self.chain else "0"
        }
        block_string = json.dumps(block, sort_keys=True).encode()
        block['hash'] = hashlib.sha256(block_string).hexdigest()

        # Actualizar balances
        for tx in transactions:
            if tx['from'] != "GENESIS":
                self.balances[tx['from']] = self.balances.get(tx['from'], 0) - tx['amount']
            self.balances[tx['to']] = self.balances.get(tx['to'], 0) + tx['amount']

        self.chain.append(block)
        return block['hash']

    def export_chain(self):
        return self.chain

# -------------------------------
# Funciones de respaldo
# -------------------------------
def guardar_wallet(wallet, nombre="fundador_wallet.json", carpeta="/storage/emulated/0/netlify"):
    datos = {
        "address": wallet.address,
        "private_key": wallet.private_key.to_string().hex(),
        "public_key": wallet.public_key.to_string().hex()
    }
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, "w") as f:
        json.dump(datos, f, indent=4)
    print(f"Wallet del fundador guardada en {ruta}")

def guardar_blockchain(chain, ruta="/storage/emulated/0/netlify/DCUP_chain.json"):
    with open(ruta, "w") as f:
        json.dump(chain.export_chain(), f, indent=4)
    print(f"Blockchain DCUP guardada en {ruta}")

# -------------------------------
# Servidor Flask del nodo fundador
# -------------------------------
app = Flask(__name__)

@app.route('/chain', methods=['GET'])
def get_chain():
    return jsonify(chain.export_chain()), 200

@app.route('/balance', methods=['GET'])
def get_balance():
    return jsonify(chain.balances), 200

if __name__ == "__main__":
    # Crear fundador y blockchain DCUP
    try:
        fundador = Wallet()
        guardar_wallet(fundador)
        chain = Blockchain(fundador, 50_000_000)  # suministro inicial en DCUP
        guardar_blockchain(chain)
    except Exception as e:
        print("Error al iniciar fundador:", e)

    # Iniciar servidor en puerto 5000
    print("Nodo fundador iniciado con 50,000,000 DCUP")
    app.run(host='0.0.0.0', port=5000)