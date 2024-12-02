# import os

# # from dotenv import load_dotenv

# # load_dotenv("dev.env")  # Important to load this before importing anything else!

# from fiber.logging_utils import get_logger
# from fiber.miner import server
# from fiber.miner.endpoints.subnet import factory_router as get_subnet_router
# from fiber.miner.middleware import configure_extra_logging_middleware

# logger = get_logger(__name__)

# app = server.factory_app(debug=True)

# app.include_router(get_subnet_router())


# # if os.getenv("ENV", "dev").lower() == "dev":
# #     configure_extra_logging_middleware(app)

# if __name__ == "__main__":
#     import uvicorn

#     uvicorn.run(app, host="0.0.0.0", port=8099)

#     # Remember to fiber-post-ip to whatever testnet you are using!


import os

# from dotenv import load_dotenv

# load_dotenv("dev.env")  # Important to load this before importing anything else!

from fiber.logging_utils import get_logger
from fiber.miner import server
from miner.endpoint import factory_router as subnet_router
from fiber.miner.middleware import configure_extra_logging_middleware
import logging
from config import get_subnet_config
logger = get_logger(__name__)

app = server.factory_app(debug=True)

app.include_router(subnet_router())


# if os.getenv("ENV", "dev").lower() == "dev":
#     configure_extra_logging_middleware(app)

if __name__ == "__main__":
    subnet_config = get_subnet_config()
    print(subnet_config)
    import uvicorn
        # File handler to save all logs to a file
    file_handler = logging.FileHandler('combined_log.txt')
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(file_handler)

    print("This will go to the log file and console.")
    logger.info("This is a logging message.")

    uvicorn.run(app, host="0.0.0.0", port=51685)

    # Remember to fiber-post-ip to whatever testnet you are using!
