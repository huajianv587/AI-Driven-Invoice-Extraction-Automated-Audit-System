from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.ui.streamlit_app import run_app


if __name__ == "__main__":
    run_app(default_view="anomaly_form")
