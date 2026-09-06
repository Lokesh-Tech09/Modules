"""
VeriFace — Module 3 Sepolia Contract Deployment Script
======================================================
Compiles and deploys VeriFaceAnchor.sol to Ethereum Sepolia Testnet using Web3.py.

Requirements:
    pip install web3 py-solc-x python-dotenv

Environment Variables (.env):
    SEPOLIA_RPC_URL="https://sepolia.infura.io/v3/YOUR_INFURA_PROJECT_ID"
    PRIVATE_KEY="0xYOUR_TESTNET_PRIVATE_KEY"
    ETHERSCAN_API_KEY="YOUR_ETHERSCAN_API_KEY" (optional)

Usage:
    python member3_blockchain/deploy_contract.py
    python member3_blockchain/deploy_contract.py --dry-run
"""

import argparse
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT_PATH = os.path.join(PROJECT_ROOT, "member3_blockchain", "contracts", "VeriFaceAnchor.sol")
BUILD_DIR = os.path.join(PROJECT_ROOT, "member3_blockchain", "contracts", "build")


def compile_contract(contract_source_path: str):
    """Compile Solidity source using solcx."""
    try:
        from solcx import compile_standard, install_solc
        install_solc("0.8.20")
    except ImportError:
        print("[ERROR] py-solc-x not installed. Run: pip install py-solc-x")
        return None, None

    with open(contract_source_path, "r", encoding="utf-8") as f:
        source = f.read()

    input_json = {
        "language": "Solidity",
        "sources": {"VeriFaceAnchor.sol": {"content": source}},
        "settings": {
            "outputSelection": {
                "*": {
                    "*": ["abi", "metadata", "evm.bytecode", "evm.sourceMap"]
                }
            }
        },
    }

    print("[INFO] Compiling VeriFaceAnchor.sol with solc 0.8.20...")
    compiled = compile_standard(input_json, solc_version="0.8.20")
    contract_data = compiled["contracts"]["VeriFaceAnchor.sol"]["VeriFaceAnchor"]
    abi = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]

    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(os.path.join(BUILD_DIR, "VeriFaceAnchor.json"), "w", encoding="utf-8") as f:
        json.dump({"abi": abi, "bytecode": bytecode}, f, indent=2)

    print(f"[SUCCESS] Compiled successfully. Artifact saved to: {BUILD_DIR}/VeriFaceAnchor.json")
    return abi, bytecode


def deploy_contract(rpc_url: str, private_key: str, dry_run: bool = False):
    """Deploy compiled contract to Sepolia testnet."""
    if dry_run:
        print("[DRY RUN] Simulation mode — skipping live blockchain deployment.")
        mock_contract_address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
        print(f"[DRY RUN] Simulated deployed contract address: {mock_contract_address}")
        return mock_contract_address

    try:
        from web3 import Web3
    except ImportError:
        print("[ERROR] web3 library not installed. Run: pip install web3")
        return None

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"[ERROR] Could not connect to RPC URL: {rpc_url}")
        return None

    chain_id = w3.eth.chain_id
    account = w3.eth.account.from_key(private_key)
    sender_address = account.address
    balance = w3.eth.get_balance(sender_address)

    print(f"[INFO] Connected to Chain ID: {chain_id}")
    print(f"[INFO] Deployer Address: {sender_address}")
    print(f"[INFO] Balance: {w3.from_wei(balance, 'ether')} ETH")

    if balance == 0:
        print("[ERROR] Deployer account has 0 ETH. Please request Sepolia faucet ETH from:")
        print("        https://sepoliafaucet.com or https://faucets.chain.link/sepolia")
        return None

    abi, bytecode = compile_contract(CONTRACT_PATH)
    if not abi or not bytecode:
        return None

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(sender_address)

    print("[INFO] Building deploy transaction...")
    tx = contract.constructor().build_transaction({
        "chainId": chain_id,
        "from": sender_address,
        "nonce": nonce,
        "gasPrice": w3.eth.gas_price,
    })

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
    print("[INFO] Broadcasting transaction to Sepolia...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"[INFO] Transaction sent! Tx Hash: {w3.to_hex(tx_hash)}")
    print("[INFO] Waiting for receipt...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    contract_address = receipt.contractAddress
    print("\n" + "=" * 60)
    print("  CONTRACT DEPLOYED SUCCESSFULLY!")
    print("=" * 60)
    print(f"  Contract Address: {contract_address}")
    print(f"  Block Number:     {receipt.blockNumber}")
    print(f"  Gas Used:         {receipt.gasUsed}")
    print(f"  Etherscan Link:   https://sepolia.etherscan.io/address/{contract_address}")
    print("=" * 60 + "\n")
    print("Add this to your .env file:")
    print(f"SEPOLIA_CONTRACT_ADDRESS={contract_address}")

    return contract_address


def main():
    parser = argparse.ArgumentParser(description="VeriFace Sepolia Contract Deployment")
    parser.add_argument("--dry-run", action="store_true", help="Simulate deployment without spending testnet ETH")
    parser.add_argument("--rpc", default=os.getenv("SEPOLIA_RPC_URL", "https://rpc.sepolia.org"))
    parser.add_argument("--key", default=os.getenv("PRIVATE_KEY", ""))
    args = parser.parse_args()

    if not args.dry_run and not args.key:
        print("[WARNING] No PRIVATE_KEY provided in .env or arguments. Defaulting to --dry-run mode.")
        args.dry_run = True

    deploy_contract(args.rpc, args.key, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
