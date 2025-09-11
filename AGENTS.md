# AGENTS.md

> A concise, agent-oriented guide to hacking on this project.
> Format reference: AGENTS.md open format.

SITUATION: You are an expert Python developer tasked with extending and maintaining a hardware
automation toolkit for Apricorn secure drives. The repository models device behaviour with a
Finite State Machine (FSM) and orchestrates hardware like Phidgets relays and a Logitech webcam.

AUDIENCE: Developers who will maintain this code in the future, including those who weren't
involved in initial development

Please follow these instructions carefully:
1. Understand the Goal: operations should respect the device's state machine and
hardware constraints.
2. Code is Illustrative: example snippets in this guide are templates; adapt names and imports
to actual modules.
3. Do Not Copy-Paste Blindly: integrate logic thoughtfully and preserve module boundaries
(controllers vs. utils, etc.).
4. Follow the Plan's Logic: implement concepts described in INSTRUCTIONS.md when provided.

## Project snapshot

- Name: **flight-control** (hardware automation toolkit).
- Primary entrypoint: `automation_toolkit.py` (initialises global controller, FSM, session).
- Python: **3.12** (minimum 3.8).
- Key libs: `numpy`, `opencv-python`, `phidget22`, `pygraphviz`, `pynput`, `transitions`, `usb_tool`.

## Setup commands

```bash
# Create venv & activate
python -m venv .venv && source .venv/bin/activate

# Install dependencies (online)
pip install -r install/requirements.txt
```

Graphviz is required for FSM diagram generation. Hardware drivers for Phidgets and the webcam must
be installed separately.

## Run / Dev

```bash
# Global controller & FSM instance
python automation_toolkit.py

# Camera & ROI tuning GUI
python tools/configuration_console.py

# Generate FSM diagram (requires Graphviz)
python tools/generate_fsm_diagram.py
```

## Tests

```bash
pytest -q
```

Tests cover the FSM, barcode scanner, webcam, phidget controller, and unified controller.

## Code style & tooling

FORMAT:
- Follow standard **PEP 8** style; keep lines ≤88 chars.
- Use clear, descriptive naming conventions
- Include meaningful comments explaining the "why" behind complex logic
- Follow the principle of least surprise
- Implement appropriate error handling with informative messages
- Organize code with logical separation of concerns
FOUNDATIONS:
- Prioritize readability over clever optimizations
- Include comprehensive input validation
- Implement proper exception handling
- Use consistent patterns throughout
- Create modular components with clear responsibilities
- Include unit tests that document expected behavior
TOOLS:
- No pre-commit hooks; run `pytest` before committing.

## Project structure (agent-relevant)

- `controllers/` — FSM logic, webcam and Phidgets controllers, unified controller.
- `utils/` — Helper modules, configuration JSON, bundled binaries.
- `tools/` — GUI/CLI utilities (configuration console, FSM diagram generator, HSV checker).
- `scripts/` — Standalone scripts like `stress_loop_test.py`.
- `tests/` — Pytest suite.

## Configuration

Configuration JSON files live in `utils/config/` (e.g., `device_properties.json`,
`hardware_configuration_settings.json`). Update hardware settings or device properties
here; avoid committing secrets or hardware-specific credentials.

## Conventions & gotchas

- Hardware access (Phidgets board, webcam) is assumed; mock or guard in tests when absent.
- Logging writes to `logs/<timestamp>/`; keep logs free of sensitive info.
- Clean up hardware resources with `at.close()` when finished.

## What to do when adding features

1. Add tests for new functionality.
2. Keep configuration and hardware data in JSON under `utils/config/`.
3. Reuse existing controllers and utilities instead of duplicating logic.
4. Ensure `pytest` passes before submitting your changes.

---