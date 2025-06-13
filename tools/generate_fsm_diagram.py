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

def create_diagram(machine_instance, filename, title=""):
    """
    Generates a diagram from a machine instance.
    """
    print(f"Generating diagram: {filename}...")
    try:
        # get_graph() is a method of GraphMachine, not the standard Machine.
        # It accepts a 'title' parameter to be displayed on the diagram.
        graph = machine_instance.get_graph(title=title)
        graph.draw(filename, prog='dot')
        print(f" -> '{filename}' saved successfully.")
    except (AttributeError, ImportError, Exception) as e: # Broader exception catch
        print("\n--- ERROR ---")
        print(f"Could not generate diagram '{filename}'. This is likely because the FSM was not loaded in diagram mode or a required library is missing.")
        print(f"Original error: {e}")
        print("Please ensure 'pygraphviz' is installed (`pip install pygraphviz`) and you have the Graphviz system package.")
        sys.exit(1)

# --- Main execution block ---
if __name__ == "__main__":
    os.environ['FSM_DIAGRAM_MODE'] = 'true'

    from controllers.flight_control_fsm import SimplifiedDeviceFSM
    from transitions.extensions import GraphMachine
    from controllers.unified_controller import UnifiedController
    from typing import cast

    print("Initializing FSM...")
    mock_at = MockUnifiedController()

    # Create the full FSM instance using the new declarative __init__
    full_fsm_instance = SimplifiedDeviceFSM(at_controller=cast(UnifiedController, mock_at))

    # 1. Generate the complete, detailed diagram. This will now be correct and complete.
    create_diagram(full_fsm_instance.machine, 'fsm_diagram_full_detail.png', title="Full FSM Diagram")

    # 2. Generate a simplified, but still verbose, diagram
    print("\nCreating a simplified FSM instance for a high-level diagram...")
    
    high_level_machine = GraphMachine(
        # model=full_fsm_instance, # <-- REMOVE THIS LINE
        states=full_fsm_instance.STATES,
        initial=full_fsm_instance.state,
        auto_transitions=False,
        graph_engine='pygraphviz',
        send_event=True
    )

    # Iterate through all the transitions defined in our new list
    for transition_config in full_fsm_instance.transition_config:
        source = transition_config['source']
        dest = transition_config['dest']

        # The key filter: skip self-loops
        if source == dest:
            continue
        
        # Build a useful label for the diagram
        label = transition_config['trigger']
        if 'conditions' in transition_config:
            conditions = transition_config['conditions']
            if not isinstance(conditions, list):
                conditions = [conditions]
            
            condition_names = ", ".join(c for c in conditions)
            label += f'\n[{condition_names}]'

        # Add the filtered and labeled transition to our high-level machine
        if isinstance(source, list):
            for src in source:
                # Pass the simple string and ignore the type checker warning
                high_level_machine.add_transition(trigger=transition_config['trigger'], source=src, dest=dest, label=label) # type: ignore
        else:
            # Pass the simple string and ignore the type checker warning
            high_level_machine.add_transition(trigger=transition_config['trigger'], source=source, dest=dest, label=label) # type: ignore

    create_diagram(high_level_machine, 'fsm_diagram_high_level.png', title="High-Level FSM Diagram (State Changes Only)")