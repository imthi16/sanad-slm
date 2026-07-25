import sys
from pathlib import Path

# data scripts are a script-style package (imported as top-level modules, like the pipeline does)
sys.path.insert(0, str(Path(__file__).parents[1] / "data" / "scripts"))
# train/ is the same shape — sft.py imports chat_template as a top-level module
sys.path.insert(0, str(Path(__file__).parents[1] / "train"))
# registry/ likewise: sft.py and merge.py both sys.path-insert it to reach artifact_manifest
sys.path.insert(0, str(Path(__file__).parents[1] / "registry"))
