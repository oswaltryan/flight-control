# Flight Control - Hardware Automation Toolkit

This project is a comprehensive automation and testing toolkit designed for interacting with and validating Apricorn secure drives. It provides a state-driven framework for executing complex test sequences involving physical hardware interaction.

The system is built around a central **Finite State Machine (FSM)** that models the device's operational states. It uses a `UnifiedController` to orchestrate commands to various hardware components, including Phidgets for relay/button control and a Logitech webcam for visual verification of LED states.

## Key Features

-   **State-Driven Control:** Utilizes a robust Finite State Machine (`transitions` library) to manage device states, ensuring that actions are only performed when the device is in a valid state.
-   **Hardware Abstraction:** A `UnifiedController` provides a simple, unified API for complex hardware interactions, abstracting away the specifics of Phidgets and camera controllers.
-   **Visual Verification:** Leverages OpenCV to visually confirm device states by reading the color and patterns of its LEDs in real-time.
-   **Physical Interaction:** Controls relays and simulates button presses via a Phidgets I/O board.
-   **Configuration-Driven:** Device properties, camera settings, and ROI coordinates are managed via external JSON files, allowing for easy updates without changing code.
-   **Utility Tools:** Includes standalone GUI and command-line tools for camera tuning, ROI calibration, and generating documentation.

## Directory Structure

A brief overview of the key directories within the `flight-control` project.

```text
flight-control/
├── controllers/          # Core logic for FSM, camera, and Phidgets.
├── docs/                 # Documentation and generated diagrams.
├── logs/                 # Output logs from test runs, organized by timestamp.
├── install/              # Contains requirements and downloaded packages for offline setup.
│   ├── requirements.txt
│   └── offline_packages/
├── scripts/              # Standalone helper scripts for specific tasks.
├── tests/                # All pytest unit and integration tests.
├── tools/                # Standalone utility tools (e.g., GUI apps for tuning).
├── utils/                # Shared helper modules, configs, and bundled binaries.
│   ├── config/           # Contains json files used to configure device and camera properties.
│   └── fio/              # Bundled FIO binaries for performance testing.
├── usb_tool/             # Source code for the local usb-tool module.
├── automation_toolkit.py # Main global instance manager for easy script access.
└── setup.py              # Defines the local usb-tool as an installable Python package.
```

## Prerequisites For Graph Generation

-   Python 3.8+
-   `pip` (Python package installer)
-   **Graphviz** (System-level package): Required only for generating FSM diagrams.
    -   **Windows:** Download from the official website and add to your system's PATH.
    -   **macOS:** `brew install graphviz`
    -   **Linux (Ubuntu/Debian):** `sudo apt-get install graphviz`

---

## Installation

This project requires Python 3.8 or higher. It is highly recommended to use a virtual environment to manage dependencies.

**Note on OS Compatibility:** This project has a dependency on `pywin32`, which is specific to Windows operating systems. While the core Python components are generally OS-agnostic, full functionality, especially related to certain hardware interactions, may be limited or unavailable on non-Windows platforms.

### Steps

1.  **Install `uv`:**
    If you don't have `uv` installed, you can install it using `pipx` (recommended) or `pip`:
    ```bash
    # Linux/Windows
    pip install uv
    # macOS
    brew install uv
    ```

2.  **Clone the repository:**
    ```bash
    git clone <your-repo-directory> flight-control
    cd flight-control
    ```

3.  **Create and activate a virtual environment using `uv`:**
    ```bash
    uv venv venv
    
    # On Windows:
    .venv\Scripts\activate
    # On macOS/Linux:
    source .venv/bin/activate
    ```

4.  **Install project dependencies using `uv`:**
    This command will install all required Python packages listed in `pyproject.toml`, including local packages.
    ```bash
    uv pip sync . --no-index --find-links=./install/offline_packages
    ```

5.  **Install Graphviz (System-level prerequisite for FSM diagram generation):**
    Graphviz is required only if you plan to generate Finite State Machine diagrams. It needs to be installed at the system level.

    *   **Windows:** Download and install from the [official Graphviz website](https://graphviz.org/download/) and ensure it's added to your system's PATH.
    *   **macOS:** `brew install graphviz`
    *   **Linux (Ubuntu/Debian):** `sudo apt-get install graphviz`

---

## Configuration

This project relies on external JSON files for configuration:

-   **`utils/config/device_properties.json`**: Contains model-specific information like firmware versions, PIN length requirements, and FIPS levels.
-   **`utils/config/camera_hardware_settings.json`**: Stores camera settings (focus, exposure) and the crucial **Region of Interest (ROI)** coordinates for each LED.

To adjust camera settings or ROIs, you can either edit `camera_hardware_settings.json` directly or use the provided GUI tool.

## Usage & Key Scripts

Several utility scripts are provided in the `tools/` and `scripts/` directories to aid in setup and debugging.

-   **Camera & ROI Tuning (GUI):**
    A graphical tool to fine-tune camera settings (focus, exposure) and interactively set the LED ROI coordinates.
    ```bash
    python tools/configuration_console.py
    ```

-   **Generate FSM Diagrams:**
    This script generates visual diagrams of the Finite State Machine, which are saved to the `docs/` folder. (Requires Graphviz).
    ```bash
    python tools/generate_fsm_diagram.py
    ```
    
-   **Run Stress Loop Testing:**
    This script will test the device under different conditions and durations based on user input.
    ```bash
    python scripts/stress_loop_test.py
    ```

## Running Unit Tests

To ensure the toolkit is functioning correctly, you can run the suite of unit tests using `pytest`.

```bash
# From the project root directory
pytest
```