import json
from pathlib import Path
from typing import Any

from scalecodec import ScaleBytes, ScaleType
from scalecodec.base import RuntimeConfiguration
from scalecodec.type_registry import load_type_registry_preset
from substrateinterface import Keypair

from fiber import SubstrateInterface
from fiber.chain import chain_utils as utils
from fiber.chain import type_registries
from fiber.logging_utils import get_logger

logger = get_logger(__name__)

def query_substrate(
    substrate: SubstrateInterface, module: str, method: str, params: list[Any], return_value: bool = True
) -> tuple[SubstrateInterface, Any]:
    try:
        query_result = substrate.query(module, method, params)

        return_val = query_result.value if return_value else query_result

        return substrate, return_val
    except Exception as e:
        logger.error(f"Query failed with error: {e}. Reconnecting and retrying.")

        substrate = SubstrateInterface(url=substrate.url)

        query_result = substrate.query(module, method, params)

        return_val = query_result.value if return_value else query_result

        return substrate, return_val
    
def _query_subtensor(
    substrate: SubstrateInterface,
    name: str,
    block: int | None = None,
    params: int | None = None,
) -> ScaleType:
    return substrate.query(
        module="SubtensorModule",
        storage_function=name,
        params=params,  # type: ignore
        block_hash=(None if block is None else substrate.get_block_hash(block)),  # type: ignore
    )
    
substrate = SubstrateInterface(
    ss58_format=42,
    use_remote_preset=True,
    url="wss://entrypoint-finney.opentensor.ai:443",
)
    

    
ans = _query_subtensor(
    substrate=substrate,
    name = "MinAllowedWeights",
    params = [5]
)

print(ans)



