# Directory: tools
# Filename: generate_fsm_diagram.py

import os
import sys
import inspect
from typing import cast, Dict, Any

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
    
class MockTestSession:
    """A mock class to satisfy the FSM's type hint for its session."""
    pass

def create_diagram(machine_instance, filename, title=""):
    """
    Generates a diagram from a machine instance.
    """
    print(f"Generating diagram: {filename}...")
    try:
        graph = machine_instance.get_graph(title=title)
        graph.draw(filename, prog='dot')
        print(f" -> '{filename}' saved successfully.")
    except (AttributeError, ImportError, Exception) as e:
        print("\n--- ERROR ---")
        print(f"Could not generate diagram '{filename}'. This is likely because the FSM was not loaded in diagram mode or a required library is missing.")
        print(f"Original error: {e}")
        print("Please ensure 'pygraphviz' is installed (`pip install pygraphviz`) and you have the Graphviz system package.")
        sys.exit(1)

def build_transition_label(transition_config: Dict[str, Any]) -> str:
    """
    Builds a descriptive label for a transition, including its conditions.
    """
    label = transition_config.get('trigger', 'unknown_trigger')

    if 'conditions' in transition_config:
        conditions = transition_config['conditions']
        if not isinstance(conditions, list):
            conditions = [conditions]

        condition_labels = []
        for c in conditions:
            condition_name = getattr(c, '__name__', None)
            if condition_name:
                condition_labels.append(condition_name)
            else:
                condition_labels.append(str(c))
        
        if condition_labels:
            label += f"\n[{', '.join(condition_labels)}]"

    return label

# --- Main execution block ---
if __name__ == "__main__":
    os.environ['FSM_DIAGRAM_MODE'] = 'true'

    # <<< FIX: Import TestSession for type casting >>>
    from controllers.finite_state_machine import ApricornDeviceFSM, TestSession
    from transitions.extensions import GraphMachine
    from controllers.unified_controller import UnifiedController
    from typing import cast

    DOCS_DIR = os.path.join(PROJECT_ROOT, 'docs')
    print(f"Ensuring output directory exists: {DOCS_DIR}")
    os.makedirs(DOCS_DIR, exist_ok=True)

    print("\nInitializing original FSM to access its configuration...")
    mock_at = MockUnifiedController()
    mock_session = MockTestSession()
    fsm_config_source = ApricornDeviceFSM(
        at_controller=cast(UnifiedController, mock_at),
        session_instance=cast(TestSession, mock_session)
    )

    # 1. Build and generate the complete, detailed diagram
    print("\nCreating a new FSM instance for the full detailed diagram...")
    full_detail_machine = GraphMachine(
        states=fsm_config_source.STATES,
        initial=fsm_config_source.state,
        auto_transitions=False,
        graph_engine='pygraphviz',
        send_event=True
    )

    for config in fsm_config_source.transition_config:
        label = build_transition_label(config)
        source = config['source']
        dest = config['dest']
        # The `label` kwarg is correct, but the type checker is confused.
        # We use `# type: ignore` to suppress the incorrect error.
        if isinstance(source, list):
            for src in source:
                full_detail_machine.add_transition(trigger=config['trigger'], source=src, dest=dest, label=label) # type: ignore
        else:
            full_detail_machine.add_transition(trigger=config['trigger'], source=source, dest=dest, label=label) # type: ignore

    full_diagram_path = os.path.join(DOCS_DIR, 'fsm_diagram_full_detail.png')
    create_diagram(full_detail_machine, full_diagram_path, title="Full FSM Diagram (with Conditions)")


    # 2. Build and generate the simplified, high-level diagram
    print("\nCreating a new FSM instance for the high-level diagram...")
    high_level_machine = GraphMachine(
        states=fsm_config_source.STATES,
        initial=fsm_config_source.state,
        auto_transitions=False,
        graph_engine='pygraphviz',
        send_event=True
    )

    for config in fsm_config_source.transition_config:
        source = config['source']
        dest = config['dest']

        # Skip self-loops for the high-level view
        if source == dest:
            continue
        
        label = build_transition_label(config)
        # Again, we use `# type: ignore` to handle the type checker's confusion.
        if isinstance(source, list):
            for src in source:
                high_level_machine.add_transition(trigger=config['trigger'], source=src, dest=dest, label=label) # type: ignore
        else:
            high_level_machine.add_transition(trigger=config['trigger'], source=source, dest=dest, label=label) # type: ignore

    high_level_diagram_path = os.path.join(DOCS_DIR, 'fsm_diagram_high_level.png')
    create_diagram(high_level_machine, high_level_diagram_path, title="High-Level FSM Diagram (State Changes Only)")

    # --- END OF REVISED LOGIC ---