import sys
from pathlib import Path

ANSIBLE_DIR = Path(__file__).resolve().parents[2]
# `ansible_collections.zollo.azuregos` and the generator importable without installing.
sys.path.insert(0, str(ANSIBLE_DIR))
sys.path.insert(0, str(ANSIBLE_DIR / "generator"))
