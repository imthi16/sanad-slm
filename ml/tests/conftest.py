import sys
from pathlib import Path

# data scripts are a script-style package (imported as top-level modules, like the pipeline does)
sys.path.insert(0, str(Path(__file__).parents[1] / "data" / "scripts"))
