# Directory: tools
# Filename: generate_fsm_diagram.py

import os
import sys
import inspect  # <--- ADD THIS IMPORT
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

    from controllers.flight_control_fsm import ApricornDeviceFSM
    from transitions.extensions import GraphMachine
    from controllers.unified_controller import UnifiedController
    from typing import cast

    DOCS_DIR = os.path.join(PROJECT_ROOT, 'docs')
    print(f"Ensuring output directory exists: {DOCS_DIR}")
    os.makedirs(DOCS_DIR, exist_ok=True)

    print("\nInitializing FSM...")
    mock_at = MockUnifiedController()

    full_fsm_instance = ApricornDeviceFSM(at_controller=cast(UnifiedController, mock_at))

    # 1. Generate the complete, detailed diagram
    full_diagram_path = os.path.join(DOCS_DIR, 'fsm_diagram_full_detail.png')
    create_diagram(full_fsm_instance.machine, full_diagram_path, title="Full FSM Diagram")

    # 2. Generate a simplified diagram
    print("\nCreating a simplified FSM instance for a high-level diagram...")
    
    high_level_machine = GraphMachine(
        states=full_fsm_instance.STATES,
        initial=full_fsm_instance.state,
        auto_transitions=False,
        graph_engine='pygraphviz',
        send_event=True
    )

    for transition_config in full_fsm_instance.transition_config:
        source = transition_config['source']
        dest = transition_config['dest']

        if source == dest:
            continue
        
        label = transition_config['trigger']
        
        # --- MODIFIED BLOCK TO FIX THE IDE ERROR ---
        if 'conditions' in transition_config:
            conditions = transition_config['conditions']
            if not isinstance(conditions, list):
                conditions = [conditions]
            
            label_parts = []
            for c in conditions:
                if isinstance(c, str):
                    # It's a string name like '_is_not_enrolled', which is perfect.
                    label_parts.append(c)
                elif callable(c):
                    # For callables (like lambdas), get the source code for a better label.
                    try:
                        source_code = inspect.getsource(c).strip()
                        # Clean up 'lambda _: ...' to just be '...'
                        if source_code.startswith('lambda'):
                            condition_text = source_code.split(':', 1)[-1].strip()
                            label_parts.append(condition_text)
                        else:
                            # For regular functions, fall back to the (safe) name.
                            label_parts.append(getattr(c, '__name__', 'unnamed_callable'))
                    except (TypeError, OSError):
                        # If inspect fails, fallback to safe name access.
                        label_parts.append(getattr(c, '__name__', '<callable>'))
                else:
                    label_parts.append(str(c)) # Fallback for any other type

            condition_names = ", ".join(label_parts)
            label += f'\n[{condition_names}]'
        # --- END MODIFIED BLOCK ---

        if isinstance(source, list):
            for src in source:
                high_level_machine.add_transition(trigger=transition_config['trigger'], source=src, dest=dest, label=label) # type: ignore
        else:
            high_level_machine.add_transition(trigger=transition_config['trigger'], source=source, dest=dest, label=label) # type: ignore

    high_level_diagram_path = os.path.join(DOCS_DIR, 'fsm_diagram_high_level.png')
    create_diagram(high_level_machine, high_level_diagram_path, title="High-Level FSM Diagram (State Changes Only)")