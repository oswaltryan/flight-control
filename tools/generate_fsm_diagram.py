# Directory: tools
# Filename: generate_fsm_diagram.py

import os
import sys
from typing import cast

# --- Path Setup ---
# This allows the script to be run from anywhere and still find the project modules.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# A mock class to satisfy the FSM's type hint for its controller
class MockUnifiedController:
    def __getattr__(self, name):
        def method(*args, **kwargs): return True
        return method

def create_diagram(machine_instance, filename):
    # This function requires the 'pygraphviz' library to be installed.
    # It also requires the Graphviz system package: https://graphviz.org/download/
    print(f"Generating diagram: {filename}...")
    try:
        # get_graph() is a method of GraphMachine, not the standard Machine.
        graph = machine_instance.get_graph()
        graph.draw(filename, prog='dot')
        print(f" -> '{filename}' saved successfully.")
    except (AttributeError, ImportError) as e:
        print("\n--- ERROR ---")
        print(f"Could not generate diagram. This is likely because the FSM was not loaded in diagram mode or a required library is missing.")
        print(f"Original error: {e}")
        print("Please ensure 'pygraphviz' is installed (`pip install pygraphviz`) and you have the Graphviz system package.")
        sys.exit(1)

# --- Main execution block ---
if __name__ == "__main__":
    # Set the environment variable FIRST, before any project imports.
    os.environ['FSM_DIAGRAM_MODE'] = 'true'

    # Now that the environment is set, we can safely import our project files.
    from controllers.flight_control_fsm import SimplifiedDeviceFSM
    from controllers.unified_controller import UnifiedController

    print("Initializing FSM...")
    mock_at = MockUnifiedController()

    # Create an instance of the FSM. It will now correctly use the GraphMachine.
    fsm_instance = SimplifiedDeviceFSM(at_controller=cast(UnifiedController, mock_at))

    # Pass the machine object itself to the creation function.
    create_diagram(fsm_instance.machine, 'fsm_diagram.png')