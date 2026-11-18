"""Features a tenant can switch on or off. Code only recognizes the codes listed here; values live in tenant_feature_flag, and a missing row means off."""

FEATURE_ALLOW_OVER_RECEIPT = "ALLOW_OVER_RECEIPT"
FEATURE_RETURNS = "RETURNS"
FEATURE_CROSS_DOCK = "CROSS_DOCK"
FEATURE_REPACK = "REPACK"
FEATURE_RETURNABLE_ASSET = "RETURNABLE_ASSET"
FEATURE_AI_ASSISTANT = "AI_ASSISTANT"
FEATURE_RECIPES = "RECIPES"
FEATURE_PACKING_UNIT_REPORTS = "PACKING_UNIT_REPORTS"

FEATURES: list[tuple[str, str, str]] = [
    (FEATURE_ALLOW_OVER_RECEIPT, "Allow over-receipt", "Received quantity may exceed the ordered quantity"),
    (FEATURE_RETURNS, "Returns", "Customer returns into stock and returns to suppliers"),
    (FEATURE_CROSS_DOCK, "Cross-docking", "Orders can be allocated straight from the receiving dock and shipped without putaway"),
    (FEATURE_REPACK, "Repack", "Unpack, kit, etc.: consume source items and produce new items"),
    (FEATURE_RETURNABLE_ASSET, "Returnable assets", "Ledger of pallets, crates, roll cages etc. lent to and returned by partners"),
    (FEATURE_RECIPES, "Recipes", "Bills of materials for manufactured products: cost per unit from purchase prices, cost share per component, and how many units current stock can make"),
    (FEATURE_PACKING_UNIT_REPORTS, "Purchases in packing units", "Dashboard purchase figures per SKU start in each item's largest packing unit (carton, bale...) instead of the base unit; users can still switch"),
    (FEATURE_AI_ASSISTANT, "AI assistant", "Ask questions about stock, documents and reports in plain language. Questions and the data looked up are sent to the configured AI provider"),
]

FEATURE_CODES = {code for code, _, _ in FEATURES}
FEATURE_NAMES = {code: name for code, name, _ in FEATURES}
