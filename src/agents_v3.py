"""Agent management uses the existing idempotent write transport."""
from agents_contract import CONTRACT
from monitoring_v3 import tools as contract_tools, handle as contract_handle

RESOURCE_URI = "signalbase://agents/v3/guide"


def tools():
    return contract_tools(CONTRACT)


async def handle(body, api_key, call):
    return await contract_handle(body, api_key, call, contract=CONTRACT,
                                 resource_uri=RESOURCE_URI, label="agent")
