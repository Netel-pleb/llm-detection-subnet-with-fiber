import time
import typing
import bittensor as bt

import random

# Bittensor Miner Template:
import detection

from detection.utils.weight_version import is_version_in_range

# import base miner class which takes care of most of the boilerplate
from detection.base.miner import BaseMinerNeuron
from neurons.miners.ppl_model import PPLModel

from transformers.utils import logging as hf_logging

from neurons.miners.deberta_classifier import DebertaClassifier

hf_logging.set_verbosity(40)






async def forward(
    request: detection.protocol.TextRequest
) -> detection.protocol.TextRequest:
    """
    Processes the incoming 'Textrequest' request by performing a predefined operation on the input data.
    This method should be replaced with actual logic relevant to the miner's purpose.
    Args:
        request (detection.protocol.Textrequest): The request object containing the 'texts' data.
    Returns:
        detection.protocol.Textrequest: The request object with the 'predictions'.
    The 'forward' function is a placeholder and should be overridden with logic that is appropriate for
    the miner's intended operation. This method demonstrates a basic transformation of input data.
    """
    start_time = time.time()
    # # Check if the validators version is correct
    # version_check = is_version_in_range(request.version, self.version, self.least_acceptable_version)
    # if not version_check:
    #     return request
    # input_data = request.texts
    # bt.logging.info(f"Amount of texts recieved: {len(input_data)}")
    # try:
    #     preds = self.model.predict_batch(input_data)
    # except Exception as e:
    #     bt.logging.error('Couldnt proceed text "{}..."'.format(input_data))
    #     bt.logging.error(e)
    #     preds = [0] * len(input_data)
    # preds = [[pred] * len(text.split()) for pred, text in zip(preds, input_data)]
    bt.logging.info(f"Made predictions in {int(time.time() - start_time)}s")
    bt.logging.info("Request recieved in Forward func")
    print(request)
    # request.predictions = preds
    request.predictions = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    return request