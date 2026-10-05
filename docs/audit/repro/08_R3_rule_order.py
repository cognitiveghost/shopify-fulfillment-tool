import logging
import sys

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from shopify_tool.rules import RuleEngine

rules = [
    {"name": "A (off, no priority)", "enabled": False, "conditions": [], "actions": []},
    {"name": "B (no priority)", "conditions": [], "actions": []},
    {"name": "C (priority 1000)", "priority": 1000, "conditions": [], "actions": []},
]
print("Rules page order:", [r["name"] for r in RuleEngine.execution_order(rules)])
print("Engine run order:", [r["name"] for r in RuleEngine(rules).rules])
