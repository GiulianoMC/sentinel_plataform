import subprocess
import sys
from pathlib import Path

class SemanticSearchService:
    def run_semantic_search(self):

        base_dir = Path(__file__).resolve().parent.parent.parent
        script_path = base_dir / "scripts" / "poc_busca_semantica.py"

        if not script_path.exists():
            raise FileNotFoundError(f"Script not found at {script_path}")

        result = subprocess.run(...)
        return result.stdout