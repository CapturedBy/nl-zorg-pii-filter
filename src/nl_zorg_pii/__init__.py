"""nl-zorg-pii-filter: mask Dutch personal data before it reaches an LLM, restore it after."""

from nl_zorg_pii.bsn import example_bsn, is_valid_bsn
from nl_zorg_pii.detectors import Match, default_detectors
from nl_zorg_pii.filter import MaskResult, PiiFilter

__all__ = ["MaskResult", "Match", "PiiFilter", "default_detectors", "is_valid_bsn", "example_bsn"]
__version__ = "0.1.0"
