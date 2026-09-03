"""Fixed, non-financial configuration constants.

Financial values (GST %, transport charge, payment split) are supplied
per request, as decided during planning. Nothing business-specific is
hardcoded here.
"""

COMPANY_NAME = "Gi Interior Solutions"
COMPANY_TAGLINE = "One Stop solution for all your Design needs"

# Amounts are rounded to the nearest multiple of this value in the
# final "Round-off Total" line, matching the reference quotation
# (e.g. 12,83,855 -> 12,80,000).
ROUND_OFF_STEP = 1000

CURRENCY_SYMBOL = "\u20b9"  # Rupee sign

OUTPUT_DIR = "data/generate/pdf"
