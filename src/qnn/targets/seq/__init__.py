from typing import List, Dict, Type
from .base import ISeqTarget
from .price_pct_change_seq_target import PricePctChangeSeqTarget
from .price_seq_target import PriceSeqTarget

SEQ_TARGETS: List[Type['ISeqTarget']] = [
    PricePctChangeSeqTarget,
    PriceSeqTarget,
]

SEQ_TARGETS_MAP: Dict[str, Type['ISeqTarget']] = {v.__name__: v for v in SEQ_TARGETS}
