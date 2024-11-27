import os

from dotenv import load_dotenv

load_dotenv()
import asyncio

import httpx
from cryptography.fernet import Fernet

from fiber.chain import chain_utils
from fiber.logging_utils import get_logger
from fiber.validator import client as vali_client
from fiber.validator import handshake


logger = get_logger(__name__)


async def main():
    # Load needed stuff
    wallet_name = os.getenv("WALLET_NAME", "default")
    hotkey_name = os.getenv("HOTKEY_NAME_2", "default")
    print(wallet_name, hotkey_name)
    keypair = chain_utils.load_hotkey_keypair(wallet_name, hotkey_name)
    httpx_client = httpx.AsyncClient()

    # Handshake with miner
    miner_address = "http://204.44.96.131:8099"
    miner_hotkey_ss58_address = "5EqEKRFdvmZoVhg7bhZtrzXieQrDsN6xivnVDEkxJU5TKqzs"
    symmetric_key_str, symmetric_key_uuid = await handshake.perform_handshake(
        keypair=keypair,
        httpx_client=httpx_client,
        server_address=miner_address,
        miner_hotkey_ss58_address=miner_hotkey_ss58_address,
    )

    if symmetric_key_str is None or symmetric_key_uuid is None:
        raise ValueError("Symmetric key or UUID is None :-(")
    else:
        logger.info("Wohoo - handshake worked! :)")

    payload = {
        "user_id": 12345,
        "action": "login",
        "timestamp": "2024-11-26T17:24:00Z",
        "details": {
            "ip_address": "192.168.1.1",
            "device": "mobile",
            "location": "New York"
        }
    }

    fernet = Fernet(symmetric_key_str)

    resp = await vali_client.make_non_streamed_post(
        httpx_client=httpx_client,
        server_address=miner_address,
        fernet=fernet,
        keypair=keypair,
        symmetric_key_uuid=symmetric_key_uuid,
        validator_ss58_address=keypair.ss58_address,
        miner_ss58_address=miner_hotkey_ss58_address,
        payload=payload,
        endpoint="/example-subnet-request",
    )
    resp.raise_for_status()
    logger.info(f"Example request sent! Response: {resp.text}")


if __name__ == "__main__":
    asyncio.run(main())
