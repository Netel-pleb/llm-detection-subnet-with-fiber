from fiber.chain import fetch_nodes, models
from substrateinterface import SubstrateInterface
from fiber.chain.metagraph import Metagraph

url = "wss://entrypoint-finney.opentensor.ai:443"
url = "wss://test.finney.opentensor.ai:443/"
substrate = SubstrateInterface(url = url)

# nodes = fetch_nodes.get_nodes_for_netuid(substrate, 5)
# print(nodes)

metagraph = Metagraph(
    substrate = substrate,
    netuid = 251,
    load_old_nodes = True,
)
nodes = metagraph.sync_nodes()
print(type(metagraph))
print(metagraph.netuid)
hotkeys = list(metagraph.nodes.keys())
# stake_list = [node.stake for node in metagraph.nodes.values()]
print(hotkeys)
# # print(hotkeys)
# # print(metagraph.nodes.values())
# print(stake_list)
# # stakes = [node_info['stake'] for node_info in metagraph.nodes.values() if 'stake' in node_info]
# # print(stakes)
# nodes = metagraph.sync_nodes()
# metagraph.save_nodes()



