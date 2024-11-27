# The MIT License (MIT)
# Copyright © 2024 It's AI 

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.


import copy
import torch
import asyncio
import threading
import bittensor as bt
import bittensor
from typing import List
from traceback import print_exception

from detection.base.neuron import BaseNeuron
from detection import (
    __version__, WANDB_PROJECT,
    WANDB_ENTITY, MAX_RUN_STEPS_PER_WANDB_RUN
)

import datetime as dt
import wandb
import time

import json





from substrateinterface import SubstrateInterface
from fiber.constants import FINNEY_SUBTENSOR_ADDRESS
from fiber.chain_interactions.metagraph import Metagraph
from fiber.chain_interactions.interface import get_substrate
from fiber.chain_interactions.chain_utils import load_hotkey_keypair
from substrateinterface import SubstrateInterface, Keypair
from datetime import date, datetime, timedelta, time
from fiber.chain_interactions.weights import set_node_weights, process_weights_for_netuid, convert_weights_and_uids_for_emit
from typing import Tuple
from fiber.chain_interactions.post_ip_to_chain import post_node_ip_to_chain
from fiber.chain_interactions.models import Node
import httpx
from fiber.validator import handshake, client
from cryptography.fernet import Fernet




class BaseValidatorNeuron(BaseNeuron):
    """
    Base class for Bittensor validators. Your validator should inherit from this class.
    """
    neuron_type: str = "ValidatorNeuron"

    keypair: Keypair

    last_metagraph_sync: int = 0

    @property
    def block(self):
        if not self.last_block_fetch or (datetime.now() - self.last_block_fetch).seconds >= 12:
            self.current_block = self.substrate.get_block_number(None)  # type: ignore
            self.last_block_fetch = datetime.now()
            self.attempted_set_weights = False

        return self.current_block


    def __init__(self, config=None):
        super().__init__(config=config)
        # Save a copy of the hotkeys to local memory.
        self.wandb_run = None
        self.hotkeys = copy.deepcopy(self.metagraph.hotkeys)

        # Init KeyPair to sign messages to wandb
        self.keypair = self.wallet.hotkey

        # Dendrite lets us send messages to other nodes (axons) in the network.
        self.dendrite = bt.dendrite(wallet=self.wallet)
        bt.logging.info(f"Dendrite: {self.dendrite}")

        # Set up initial scoring weights for validation
        bt.logging.info("Building validation weights.")

        # Instead of loading zero weights we take latest weights from the previous run
        # If it is first run for validator then it will be filled with zeros
        # self.scores = torch.zeros_like(self.metagraph.S, dtype=torch.float32, device=self.device)
        weight_metagraph = self.subtensor.metagraph(self.config.netuid, lite=False)
        self.scores = weight_metagraph.W[self.uid].to(self.device)

        # Init sync with the network. Updates the metagraph.
        self.sync()
        subtensor_url = FINNEY_SUBTENSOR_ADDRESS
        self.substrate = get_substrate(
            subtensor_address = subtensor_url
        )        
        self.metagraph = Metagraph(
            substrate = self.substrate,
            netuid =  self.config.netuid,
            load_old_nodes = True,
        )
        self.metagraph.sync_nodes()
        self.hotkeys = list(self.metagraph.nodes.keys())
        self.stakes = [node.stake for node in self.metagraph.nodes.values()]
        # Serve axon to enable external connections.
        if not self.config.neuron.axon_off:
            self.serve_axon()
        else:
            bt.logging.warning("axon off, not serving ip to chain.")

        self.new_wandb_run()
        # Create asyncio event loop to manage async tasks.
        self.loop = asyncio.get_event_loop()

        # Instantiate runners
        self.should_exit: bool = False
        self.is_running: bool = False
        self.thread: threading.Thread = None
        self.lock = asyncio.Lock()

    def sync_chain_nodes(self, block: int):
        # logger.info("Syncing metagraph")

        self.metagraph.sync_nodes()

        self.check_registration()

        if len(self.hotkeys) != len(self.metagraph.nodes):
            self.resize()

            if self.contest_state:
                new_miner_info = [None] * len(self.metagraph.nodes)
                length = len(self.hotkeys)
                new_miner_info[:length] = self.contest_state.miner_info[:length]

                self.contest_state.miner_info = new_miner_info

        nodes = self.metagraph_nodes()

        for uid, hotkey in enumerate(self.hotkeys):
            if hotkey != nodes[uid].hotkey:
                # hotkey has been replaced
                self.reset_miner(uid)

                if self.contest_state:
                    self.contest_state.miner_info[uid] = None

        self.hotkeys = list(self.metagraph.nodes.keys())
        self.last_metagraph_sync = block

    def sync(self):
        """
        Wrapper for synchronizing the state of the network for the given validator.
        """
        # Ensure miner or validator hotkey is still registered on the network.
        # self.check_registered()
        self.check_registration()

        try:
            if self.should_sync_metagraph():
                self.last_update = self.block
                self.resync_metagraph()
                # Parse versions for weight_check
                self.parse_versions()

            if self.should_set_weights():
                self.set_weights()

            # Always save state.
            self.save_state()
        except Exception as e:
            bt.logging.error("Coundn't sync metagraph or set weights: {}".format(e))
            bt.logging.error("If you use public RPC endpoint try to move to local node")
            time.sleep(5)

    def should_set_weights(self) -> bool:
        last_update = self.metagraph.nodes[self.keypair.ss58_address].last_updated
        blocks_elapsed = self.block - last_update
        epoch_length = self.config.neuron.epoch_length

        return blocks_elapsed >= epoch_length

    def should_sync_metagraph(self):
        """
        Check if enough epoch blocks have elapsed since the last checkpoint to sync.
        """
        # last_update = self.metagraph.last_update[self.uid]
        last_metagraph_sync = self.block
        blocks_elapsed = self.block - last_metagraph_sync
        # return (
        #     self.block - last_update
        # ) > self.config.neuron.epoch_length
        return (blocks_elapsed > self.config.neuron.epoch_length)
    
    
    
    
    
    
    async def try_handshake(
        self,
        async_client: httpx.AsyncClient,
        server_address: str,
        keypair,
        hotkey
    ) -> tuple:
        return await handshake.perform_handshake(
            async_client, server_address, keypair, hotkey
        )
    
    async def _handshake(self, node: Node, async_client: httpx.AsyncClient) -> Node:
        node_copy = node.model_copy()
        server_address = client.construct_server_address(
            node=node,
            replace_with_docker_localhost = True,
            replace_with_localhost = False,
        )

        try:
            symmetric_key, symmetric_key_uid = await self.try_handshake(
                async_client, server_address, self.keypair, node.hotkey
            )
        except Exception as e:
            # error_details = _format_exception(e)
            # logger.debug(f"Failed to perform handshake with {server_address}. Details:\n{error_details}")

            if isinstance(e, (httpx.HTTPStatusError, httpx.RequestError, httpx.ConnectError)):
                if hasattr(e, "response"):
                    # logger.debug(f"Response content: {e.response.text}")
                    pass
            return node_copy

        fernet = Fernet(symmetric_key)
        node_copy.fernet = fernet
        node_copy.symmetric_key_uuid = symmetric_key_uid
        return node_copy

    async def perform_handshakes(self, nodes: list[Node]) -> list[Node]:
        tasks = []
        shaked_nodes: list[Node] = []
        for node in nodes:
            if node.fernet is None or node.symmetric_key_uuid is None:
                tasks.append(self._handshake(node, httpx.AsyncClient))
            if len(tasks) > 50:
                shaked_nodes.extend(await asyncio.gather(*tasks))
                tasks = []

        if tasks:
            shaked_nodes.extend(await asyncio.gather(*tasks))

        nodes_where_handshake_worked = [
            node for node in shaked_nodes if node.fernet is not None and node.symmetric_key_uuid is not None
        ]
        if len(nodes_where_handshake_worked) == 0:
            # logger.info("❌ Failed to perform handshakes with any nodes!")
            pass
            return []
        # logger.info(f"✅ performed handshakes successfully with {len(nodes_where_handshake_worked)} nodes!")

        # async with await config.psql_db.connection() as connection:
        #     await insert_symmetric_keys_for_nodes(connection, nodes_where_handshake_worked)

        return shaked_nodes    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    def serve_axon(self):
        """Serve axon to enable external connections."""

        # bt.logging.info("serving ip to chain...")
        # try:
        #     self.axon = bt.axon(wallet=self.wallet, config=self.config)
        #     # self.axon = bt.axon(wallet=self.wallet, config=self.config

        #     try:
        #         self.subtensor.serve_axon(
        #             netuid=self.config.netuid,
        #             axon=self.axon,
        #         )
        #         bt.logging.info(
        #             f"Running validator {self.axon} on network: {self.config.subtensor.chain_endpoint} with netuid: {self.config.netuid}"
        #         )
        #     except Exception as e:
        #         bt.logging.error(f"Failed to serve Axon with exception: {e}")
        #         pass

        # except Exception as e:
        #     bt.logging.error(
        #         f"Failed to create Axon initialize with exception: {e}"
        #     )
        #     pass
        try:
            success = post_node_ip_to_chain(
                substrate = self.substrate,
                keypair = Keypair,
                netuid = self.netuid,
                external_ip = self.external_ip,
                external_port = self.external_port,
                coldkey_ss58_address = self.coldkey,
            )
        except Exception as e:
            pass
        
    async def concurrent_forward(self):
        coroutines = [
            self.forward()
            for _ in range(self.config.neuron.num_concurrent_forwards)
        ]
        await asyncio.gather(*coroutines)

    def run(self):
        """
        Initiates and manages the main loop for the miner on the Bittensor network. The main loop handles graceful shutdown on keyboard interrupts and logs unforeseen errors.

        This function performs the following primary tasks:
        1. Check for registration on the Bittensor network.
        2. Continuously forwards queries to the miners on the network, rewarding their responses and updating the scores accordingly.
        3. Periodically resynchronizes with the chain; updating the metagraph with the latest network state and setting weights.

        The essence of the validator's operations is in the forward function, which is called every step. The forward function is responsible for querying the network and scoring the responses.

        Note:
            - The function leverages the global configurations set during the initialization of the miner.
            - The miner's axon serves as its interface to the Bittensor network, handling incoming and outgoing requests.

        Raises:
            KeyboardInterrupt: If the miner is stopped by a manual interruption.
            Exception: For unforeseen errors during the miner's operation, which are logged for diagnosis.
        """

        # Check that validator is registered on the network.
        self.sync()

        bt.logging.info(f"Validator starting at block: {self.block}")

        # This loop maintains the validator's operations until intentionally stopped.
        try:
            while True:
                bt.logging.info(f"step({self.step}) block({self.block})")

                # Run multiple forwards concurrently.
                self.loop.run_until_complete(self.concurrent_forward())

                # Check if we should exit.
                if self.should_exit:
                    break

                # Sync metagraph and potentially set weights.
                self.sync()

                self.step += 1

        # If someone intentionally stops the validator, it'll safely terminate operations.
        except KeyboardInterrupt:
            if self.wandb_run:
                print("Finishing wandb service...")
                self.wandb_run.finish()
            self.axon.stop()
            bt.logging.success("Validator killed by keyboard interrupt.")
            exit()

        # In case of unforeseen errors, the validator will log the error and continue operations.
        except Exception as err:
            bt.logging.error("Error during validation", str(err))
            bt.logging.debug(
                print_exception(type(err), err, err.__traceback__)
            )

    def run_in_background_thread(self):
        """
        Starts the validator's operations in a background thread upon entering the context.
        This method facilitates the use of the validator in a 'with' statement.
        """
        if not self.is_running:
            bt.logging.debug("Starting validator in background thread.")
            self.should_exit = False
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
            self.is_running = True
            bt.logging.debug("Started")

    def stop_run_thread(self):
        """
        Stops the validator's operations that are running in the background thread.
        """
        if self.is_running:
            bt.logging.debug("Stopping validator in background thread.")
            if self.wandb_run:
                print("Finishing wandb service...")
                self.wandb_run.finish()
            self.should_exit = True
            self.thread.join(5)
            self.is_running = False
            bt.logging.debug("Stopped")

    def __enter__(self):
        self.run_in_background_thread()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Stops the validator's background operations upon exiting the context.
        This method facilitates the use of the validator in a 'with' statement.

        Args:
            exc_type: The type of the exception that caused the context to be exited.
                      None if the context was exited without an exception.
            exc_value: The instance of the exception that caused the context to be exited.
                       None if the context was exited without an exception.
            traceback: A traceback object encoding the stack trace.
                       None if the context was exited without an exception.
        """
        if self.is_running:
            bt.logging.debug("Stopping validator in background thread.")
            if self.wandb_run:
                print("Finishing wandb service...")
                self.wandb_run.finish()
            self.should_exit = True
            self.thread.join(5)
            self.is_running = False
            bt.logging.debug("Stopped")

    def set_weights(self):
        """
        Sets the validator weights to the metagraph hotkeys based on the scores it has received from the miners. The weights determine the trust and incentive level the validator assigns to miner nodes on the network.
        """

        # Check if self.scores contains any NaN values and log a warning if it does.
        if torch.isnan(self.scores).any():
            bt.logging.warning(
                f"Scores contain NaN values. This may be due to a lack of responses from miners, or a bug in your reward functions."
            )

        # Calculate the average reward for each uid across non-zero values.
        # Replace any NaN values with 0.
        # m = torch.nn.Softmax()
        # raw_weights = m(self.scores * 4)
        raw_weights = torch.nn.functional.normalize(self.scores, p=1, dim=0)

        bt.logging.debug("raw_weights", raw_weights)
        bt.logging.debug("raw_weight_uids", self.metagraph.uids.to("cpu"))
        # Process the raw weights to final_weights via subtensor limitations.
        (
            processed_weight_uids,
            processed_weights,
        ) = process_weights_for_netuid(
            uids=self.metagraph.uids.to("cpu"),
            weights=raw_weights.to("cpu"),
            netuid=self.config.netuid,
            # subtensor=self.subtensor,
            metagraph=self.metagraph,
        )
        bt.logging.debug("processed_weights", processed_weights)
        bt.logging.debug("processed_weight_uids", processed_weight_uids)

        # Convert to uint16 weights and uids.
        (
            uint_uids,
            uint_weights,
        ) = convert_weights_and_uids_for_emit(
            uids=processed_weight_uids, weights=processed_weights
        )
        bt.logging.debug("uint_weights", uint_weights)
        bt.logging.debug("uint_uids", uint_uids)

        # Set the weights on chain via our subtensor connection.
        # result, msg = self.subtensor.set_weights(
        #     wallet=self.wallet,
        #     netuid=self.config.netuid,
        #     uids=uint_uids,
        #     weights=uint_weights,
        #     wait_for_finalization=False,
        #     wait_for_inclusion=False,
        #     version_key=self.spec_version,
        # )
        result = set_node_weights(
            self.substrate,
            self.keypair,
            node_ids=list(range(len(self.metagraph.nodes))),
            node_weights=uint_weights,
            netuid=self.metagraph.netuid,
            validator_node_id=self.uid,
            version_key=self.spec_version,
        )
        
        if result is True:
            bt.logging.info("set_weights on chain successfully!")
        else:
            bt.logging.error(f"set_weights failed {msg}")

    def resync_metagraph(self):
        """Resyncs the metagraph and updates the hotkeys and moving averages based on the new metagraph."""
        bt.logging.info("resync_metagraph()")

        # Copies state of metagraph before syncing.
        previous_metagraph = copy.deepcopy(self.metagraph)
        
        # Sync the metagraph.
        # self.metagraph.sync(subtensor=self.subtensor)
        nodes = self.metagraph_nodes()
        
        self.metagraph.sync_nodes()
        
        self.check_registration()

        # Check if the metagraph axon info has changed.
        # if previous_metagraph.axons == self.metagraph.axons:
        #     return
        if self.hotkeys == list(self.metagraph.nodes.keys()):
            return

        bt.logging.info(
            "Metagraph updated, re-syncing hotkeys, dendrite pool and moving averages"
        )
        # Zero out all hotkeys that have been replaced.
        
        # for uid, hotkey in enumerate(self.hotkeys):
        #     if hotkey != self.metagraph.hotkeys[uid]:
        #         self.scores[uid] = 0  # hotkey has been replaced
        
        for uid, hotkey in enumerate(self.hotkeys):
            if hotkey != nodes[uid].hotkey:
                self.scores[uid] = 0  # hotkey has been replaced

        # Check to see if the metagraph has changed size.
        # If so, we need to add new hotkeys and moving averages.
        if len(self.hotkeys) != len(self.metagraph.nodes):
            # Update the size of the moving average scores.
            new_moving_average = torch.zeros((self.metagraph.n)).to(
                self.device
            )
            min_len = min(len(self.hotkeys), len(self.scores))
            new_moving_average[:min_len] = self.scores[:min_len]
            self.scores = new_moving_average

        # Update the hotkeys.
        self.hotkeys = list(self.metagraph.nodes.keys())
        self.last_metagraph_sync = self.block

    def update_scores(self, rewards: torch.FloatTensor, uids: List[int]):
        """Performs exponential moving average on the scores based on the rewards received from the miners."""

        # Check if rewards contains NaN values.
        if torch.isnan(rewards).any():
            bt.logging.warning(f"NaN values detected in rewards: {rewards}")
            # Replace any NaN values in rewards with 0.
            rewards = torch.nan_to_num(rewards, 0)

        # Compute forward pass rewards, assumes uids are mutually exclusive.
        # shape: [ metagraph.n ]
        scattered_rewards: torch.FloatTensor = self.scores.scatter(
            0, torch.tensor(uids).to(self.device), rewards
        ).to(self.device)
        bt.logging.debug(f"Scattered rewards: {rewards}")

        # Update scores with rewards produced by this step.
        # shape: [ metagraph.n ]
        alpha: float = self.config.neuron.moving_average_alpha
        self.scores: torch.FloatTensor = alpha * scattered_rewards + (
                1 - alpha
        ) * self.scores.to(self.device)
        bt.logging.debug(f"Updated moving avg scores: {self.scores}")

    def save_state(self):
        """Saves the state of the validator to a file."""
        bt.logging.info("Saving validator state.")

        # Save the state of the validator to file.
        torch.save(
            {
                "step": self.step,
                "scores": self.scores,
                "hotkeys": self.hotkeys,
            },
            self.config.neuron.full_path + "/state.pt",
        )

    def load_state(self):
        """Loads the state of the validator from a file."""
        bt.logging.info("Loading validator state.")

        # Load the state of the validator from file.
        state = torch.load(self.config.neuron.full_path + "/state.pt")
        self.step = state["step"]
        self.scores = state["scores"]
        self.hotkeys = state["hotkeys"]

    def new_wandb_run(self):
        """Creates a new wandb run to save information to."""
        # Create a unique run id for this run.
        run_id = dt.datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

        name = "validator-" + str(self.uid) + "-" + run_id
        self.wandb_run = wandb.init(
            name=name,
            project=WANDB_PROJECT,
            entity=WANDB_ENTITY,
            anonymous='must',
            config={
                "uid": self.uid,
                "hotkey": self.wallet.hotkey.ss58_address,
                "run_name": run_id,
                "version": __version__,
            },
            allow_val_change=True
        )

        bt.logging.debug(f"Started a new wandb run: {name}")

    def log_step(
            self,
            uids,
            metrics,
            rewards
    ):
        # If we have already completed X steps then we will complete the current wandb run and make a new one.     
        if self.step % MAX_RUN_STEPS_PER_WANDB_RUN == 0:
            step_log = {
                "timestamp": time.time(),
                "uids": uids.tolist(),
                "uid_metrics": {},
            }
            bt.logging.info(
                f"Validator has completed {self.step} run steps. Creating a new wandb run."
            )
            self.wandb_run.finish()
            self.new_wandb_run()

            for i, uid in enumerate(uids):
                step_log["uid_metrics"][str(uid.item())] = {
                    "uid": uid.item(),
                    "weight": self.scores[uid].item(),
                    "reward": rewards[i].item()
                }
                step_log["uid_metrics"][str(uid.item())].update(metrics[i])

            graphed_data = {
                "block": self.metagraph.block.item(),
                "uid_data": {
                    str(uids[i].item()): rewards[i].item() for i in range(len(uids))
                },
                "weight_data": {str(uid.item()): self.scores[uid].item() for uid in uids},
            }

            bt.logging.info(
                f"step_log: {step_log}"
            )
            bt.logging.info(
                f"graphed_data: {graphed_data}"
            )
            original_format_json = json.dumps(step_log)

            signed_msg = f'0x{self.keypair.sign(original_format_json).hex()}'
            bt.logging.info("Logging to Wandb")
            self.wandb_run.log(
                {
                    **graphed_data,
                    "original_format_json": original_format_json,
                    "signed_msg": signed_msg
                },
                step=self.step,
            )
            bt.logging.info("Logged")
