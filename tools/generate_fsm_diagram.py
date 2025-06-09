# Directory: scripts
# Filename: generate_fsm_diagram.py

import os
import sys
# --- THE FIX: Import 'cast' from the typing module ---
from typing import cast
# -------------------------------------------------------

# ... (Path setup and MockUnifiedController are correct)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

class MockUnifiedController:
    def __getattr__(self, name):
        def method(*args, **kwargs): return True
        return method

if __name__ == "__main__":
    from controllers.flight_control_fsm import SimplifiedDeviceFSM, DUT
    # --- We also need the real class for the cast ---
    from controllers.unified_controller import UnifiedController
    # ------------------------------------------------

    print("Initializing FSM...")
    mock_at = MockUnifiedController()

    def create_diagram(fsm_instance, filename):
        print(f"Generating diagram: {filename}...")
        graph = fsm_instance.get_graph()
        graph.show_conditions = True
        graph.show_triggers = True
        graph.draw(filename, prog='dot')
        print(f" -> '{filename}' saved successfully.")

    # Generate diagram
    fsm_diagram = SimplifiedDeviceFSM(at_controller=cast(UnifiedController, mock_at))
    # ------------------------------------------
    create_diagram(fsm_diagram, 'fsm_diagram.png')
