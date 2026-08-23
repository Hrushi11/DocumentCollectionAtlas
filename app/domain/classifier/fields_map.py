"""
Per-form field maps and text anchors (docs/02 §2, §3). Fields are opaque `f*_NN`; these maps
were built once by locating widgets on the official IRS templates (see scripts/build_fixtures).
"""
# W-2 CopyB terminal fields (several copies share these short names — read the *filled* one).
W2_FIELDS = {
    "first": "f2_05[0]", "last": "f2_06[0]",
    "employer": "f2_03[0]", "wages": "f2_09[0]", "ssn": "f2_01[0]",
}
# 1040 name row.
F1040_FIELDS = {
    "tp_first": "f1_04[0]", "tp_last": "f1_05[0]",
    "sp_first": "f1_07[0]", "sp_last": "f1_08[0]",
}

# Type detection uses flexible token-sets, not exact multiword anchors — vendor layouts reflow
# text and split phrases across lines (docs/02 §2.1).
W2_TOKENS = ["w-2", "wage and tax", "wages, tips", "social security wages", "medicare"]
F1040_TOKENS = ["u.s. individual income tax return", "form 1040"]

MIN_CHARS = 20          # below this (and no form fields) ⇒ unreadable
YEAR_MIN, YEAR_MAX = 2000, 2035
