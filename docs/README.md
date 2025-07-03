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

You can install the necessary packages using either an online or offline method.

### Online Installation (Recommended)

This is the standard method for a machine with an internet connection.

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd flight-control
    ```

2.  **Install all dependencies:**
    This command installs both the public packages from `requirements.txt` and your local `usb-tool` package.
    ```bash
    pip install -r ./install/requirements.txt
    pip install .
    ```

### Offline Installation

1.  **Extract the Bundle:**
    Unzip the project files on the offline machine.

2.  **Install from Local Files:**
    Navigate your terminal into the `flight-control` directory and run the install command. The `--no-index` and `--find-links` flags are critical here.
    ```bash
    pip install -r requirements.txt --no-index --find-links=./install/offline_packages
    ```

This will install all required packages using only the files you downloaded.

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