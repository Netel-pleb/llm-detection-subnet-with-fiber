import torch
import random
import bittensor as bt
from typing import List
from fiber.chain.models import Node

def check_uid_availability(
    # metagraph: "bt.metagraph.Metagraph", uid: int, vpermit_tao_limit: int
    stakes: List[int], uid: int, vpermit_tao_limit: int
) -> bool:
    """Check if uid is available. The UID should be available if it is serving and has less than vpermit_tao_limit stake
    Args:
        metagraph (:obj: bt.metagraph.Metagraph): Metagraph object
        uid (int): uid to be checked
        vpermit_tao_limit (int): Validator permit tao limit
    Returns:
        bool: True if uid is available, False otherwise
    """

    # Filter non serving axons.
    # if not metagraph.axons[uid].is_serving:
    #     return False
    
    # Filter validator permit > 1024 stake.
    # if metagraph.validator_permit[uid]:
    #     if metagraph.S[uid] > vpermit_tao_limit:
    #         return False
    if stakes[uid] > vpermit_tao_limit:
        return False
        
    # Available otherwise.
    return True


def get_random_uids(
        self, k: int, exclude: List[int] = None
) -> torch.LongTensor:
    """Returns k available random uids from the metagraph.
    Args:
        k (int): Number of uids to return.
        exclude (List[int]): List of uids to exclude from the random sampling.
    Returns:
        uids (torch.LongTensor): Randomly sampled available uids.
    Notes:
        If `k` is larger than the number of available `uids`, set `k` to the number of available `uids`.
    """
    candidate_uids = []
    avail_uids = []

    for uid in range(self.metagraph.n.item()):

        uid_is_available = check_uid_availability(
            # self.metagraph, uid, self.config.neuron.vpermit_tao_limit
            self.stakes, uid, self.config.neuron.vpermit_tao_limit
        )
        uid_is_not_excluded = exclude is None or uid not in exclude

        if uid_is_available:
            avail_uids.append(uid)
            if uid_is_not_excluded:
                candidate_uids.append(uid)

    # Check if candidate_uids contain enough for querying, if not grab all avaliable uids
    available_uids = candidate_uids

    # If k is larger than the number of available uids, set k to the number of available uids.
    k = min(k, len(available_uids))
    uids = torch.tensor(random.sample(available_uids, k))
    return uids



def get_random_nodes(
        self, k: int, nodes: list[Node], exclude: List[int] = None
) -> torch.LongTensor:
    """Returns k available random uids from the metagraph.
    Args:
        k (int): Number of uids to return.
        exclude (List[int]): List of uids to exclude from the random sampling.
    Returns:
        uids (torch.LongTensor): Randomly sampled available uids.
    Notes:
        If `k` is larger than the number of available `uids`, set `k` to the number of available `uids`.
    """
    avail_nodes = []
    for node in nodes:
        if node.stake >= self.config.neuron.vpermit_tao_limit and node.node_id not in exclude:
            avail_nodes.append(node)

    k = min(k, len(avail_nodes))
    seleted_nodes = random.sample(avail_nodes, k)
    return seleted_nodes
