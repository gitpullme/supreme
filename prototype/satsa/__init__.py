"""SAT-SA prototype package."""
from .ledger import Ledger
from .generator import generate
from .detectors import run_all_detectors
from .scoring import score_entities
from .validate import validate
from .config import load as load_config
from . import embeddings

__all__ = ["Ledger", "generate", "run_all_detectors", "score_entities",
           "validate", "load_config", "embeddings"]
__version__ = "0.2.0"
