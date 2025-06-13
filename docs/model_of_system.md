## State Machine Documentation: SimplifiedDeviceFSM

### 1. Overview

This document describes the state machine for the `SimplifiedDeviceFSM`. The FSM manages the operational states of a secure hardware device. It handles everything from initial power-on and configuration to user/admin access, feature toggling, and security-related states like brute force protection.

The FSM logic is implemented using the `transitions` Python library. It relies on a `DUT` (Device Under Test) object to model and track the device's properties and state, such as enrolled PINs, feature settings, and security counters.

### 2. State Descriptions

The FSM is composed of the following states:

| State | Description |
| :--- | :--- |
| **OFF** | The initial state. The device is powered off and disconnected. |
| **POWER_ON_SELF_TEST** | A transient state entered immediately after power-on. The device performs a startup self-test. It will transition to an appropriate idle state or an error state based on the test result and device configuration. |
| **OOB_MODE** | "Out-Of-Box" Mode. The state for a new or factory-reset device where no Admin PIN has been enrolled yet. The device is waiting for initial setup. |
| **STANDBY_MODE** | The default "idle" state for an enrolled (configured) device. The device is locked and awaiting a valid PIN or command. |
| **USER_FORCED_ENROLLMENT** | A special state where an administrator has configured the device to require user enrollment before it can be used normally. It behaves like `STANDBY_MODE` but enforces user setup. |
| **UNLOCKED_ADMIN** | The device has been successfully unlocked with the Admin PIN. The storage is accessible, and the device is enumerated by the host OS. |
| **UNLOCKED_USER** | The device has been successfully unlocked with a User PIN. The storage is accessible, and the device is enumerated by the host OS. |
| **ADMIN_MODE** | A special configuration mode for administrators. In this state, device features can be toggled, and PINs or counters can be enrolled. The storage is not accessible. |
| **PIN_ENROLLMENT** | A transient sub-state of `ADMIN_MODE` where the device is actively waiting for a new PIN to be entered and confirmed. |
| **COUNTER_ENROLLMENT** | A transient sub-state of `ADMIN_MODE` where the device is actively waiting for a new numeric value for a counter (e.g., Brute Force attempts). |
| **DIAGNOSTIC_MODE** | A state for performing device diagnostics. |
| **BRUTE_FORCE** | The device has entered a protected state due to too many failed unlock attempts. It requires special recovery or will become bricked. |
| **BRICKED** | A terminal state where the device is permanently disabled due to a failed brute force recovery. |
| **ERROR_MODE** | A terminal state entered if the Power-On-Self-Test (POST) fails. The device is non-operational. |

### 3. State Transition Table

The following table details every possible transition within the state machine.

*   **Trigger**: The event that causes the state change.
*   **Source State**: The state the machine must be in for the trigger to be valid.
*   **Destination State**: The state the machine moves to upon a successful transition.
*   **Conditions**: Pre-requisites that must be met for the transition to occur. These are checked before any actions are taken.
*   **Actions / Callbacks**: Functions that are executed during the transition. `(before)` actions run before the state changes, and `(on_enter)` actions run immediately after entering the new state.

| Trigger (Event) | Source State(s) | Destination State | Conditions | Actions / Callbacks |
| :--- | :--- | :--- | :--- | :--- |
| **power_on** | `OFF` | `POWER_ON_SELF_TEST` | (none) | `(before)` `_do_power_on` <br/> `(on_enter)` `on_enter_POWER_ON_SELF_TEST` |
| **power_off** | `*` (Any State) | `OFF` | (none) | `(on_enter)` `on_enter_OFF` |
| **post_fail** | `POWER_ON_SELF_TEST` | `ERROR_MODE` | (none) | (none) |
| **post_pass** | `POWER_ON_SELF_TEST` | `OOB_MODE` | No Admin PIN is enrolled (`not DUT.adminPIN`). | `(on_enter)` `on_enter_OOB_MODE` |
| | | `USER_FORCED_ENROLLMENT` | User Forced Enrollment is active (`DUT.userForcedEnrollment`). | (none) |
| | | `BRUTE_FORCE` | Brute force counter is zero (`DUT.bruteForceCounter == 0`). | `(on_enter)` `on_enter_BRUTE_FORCE` |
| | | `STANDBY_MODE` | An Admin PIN is enrolled (`DUT.adminPIN`). | `(on_enter)` `on_enter_STANDBY_MODE` |
| **enroll_admin** | `OOB_MODE` | `ADMIN_MODE` | (none) | `(before)` `_admin_enrollment`<br/>`(on_enter)` `on_enter_ADMIN_MODE` |
| | `ADMIN_MODE` | `PIN_ENROLLMENT` | (none) | `(before)` `_admin_enrollment`<br/>`(on_enter)` `on_enter_PIN_ENROLLMENT` |
| **unlock_admin** | `STANDBY_MODE`, `USER_FORCED_ENROLLMENT` | `UNLOCKED_ADMIN` | (none) | `(before)` `_enter_admin_pin`<br/>`(on_enter)` `on_enter_UNLOCKED_ADMIN` |
| **unlock_user** | `STANDBY_MODE` | `UNLOCKED_USER` | (none) | `(before)` `_enter_user_pin`<br/>`(on_enter)` `on_enter_UNLOCKED_USER` |
| | `USER_FORCED_ENROLLMENT` | `UNLOCKED_USER` | At least one User PIN is enrolled. | `(before)` `_enter_user_pin`<br/>`(on_enter)` `on_enter_UNLOCKED_USER` |
| **admin_mode_login** | `STANDBY_MODE`, `USER_FORCED_ENROLLMENT` | `ADMIN_MODE` | (none) | `(before)` `_enter_admin_mode`<br/>`(on_enter)` `on_enter_ADMIN_MODE` |
| **lock_admin** | `ADMIN_MODE` | `STANDBY_MODE` | (none) | `(before)` `_press_lock_button`<br/>`(on_enter)` `on_enter_STANDBY_MODE` |
| | `ADMIN_MODE` | `USER_FORCED_ENROLLMENT` | (none) | `(before)` `_press_lock_button` |
| | `UNLOCKED_ADMIN` | `STANDBY_MODE` | (none) | `(before)` `_press_lock_button`<br/>`(on_enter)` `on_enter_STANDBY_MODE` |
| | `UNLOCKED_ADMIN` | `USER_FORCED_ENROLLMENT` | (none) | `(before)` `_press_lock_button` |
| **lock_user** | `UNLOCKED_USER` | `STANDBY_MODE` | (none) | `(before)` `_press_lock_button`<br/>`(on_enter)` `on_enter_STANDBY_MODE` |
| | `UNLOCKED_USER` | `USER_FORCED_ENROLLMENT` | (none) | `(before)` `_press_lock_button` |
| **fail_unlock** | `STANDBY_MODE`, `USER_FORCED_ENROLLMENT` | `STANDBY_MODE` | Attempts remaining are not at a brute force threshold. | `(before)` `_enter_invalid_pin` |
| | `STANDBY_MODE`, `USER_FORCED_ENROLLMENT` | `BRUTE_FORCE` | Attempts have reached a brute force threshold (midpoint or final). | `(before)` `_enter_invalid_pin`<br/>`(on_enter)` `on_enter_BRUTE_FORCE` |
| **user_reset** | `ADMIN_MODE` | `OOB_MODE` | (none) | `(before)` `_do_user_reset`<br/>`(on_enter)` `on_enter_OOB_MODE` |
| | `OOB_MODE` | `OOB_MODE` (Loop) | Provision Lock is inactive. | `(on_enter)` `on_enter_OOB_MODE` |
| | `STANDBY_MODE`, `USER_FORCED_ENROLLMENT`, `BRUTE_FORCE` | `OOB_MODE` | Provision Lock is inactive. | `(on_enter)` `on_enter_OOB_MODE` |
| **last_try_login** | `BRUTE_FORCE` | `STANDBY_MODE` | At the "last try" threshold (`bruteForceCurrent == bruteForceCounter/2`). | `(before)` `_enter_last_try_pin`<br/>`(on_enter)` `on_enter_STANDBY_MODE` |
| **admin_recovery_failed** | `BRUTE_FORCE` | `BRICKED` | (none) | (none) |
| **self_destruct** | `STANDBY_MODE`, `USER_FORCED_ENROLLMENT`| `UNLOCKED_ADMIN` | (none) | `(before)` `_enter_self_destruct_pin`<br/>`(on_enter)` `on_enter_UNLOCKED_ADMIN` |
| **enroll_user** | `USER_FORCED_ENROLLMENT`| `STANDBY_MODE` | (none) | `(before)` `_user_enrollment`<br/>`(on_enter)` `on_enter_STANDBY_MODE`|
| | `ADMIN_MODE` | `PIN_ENROLLMENT` | An empty user slot exists. | `(before)` `_user_enrollment`<br/>`(on_enter)` `on_enter_PIN_ENROLLMENT`|
| **enter_diagnostic_mode** | `OOB_MODE`, `STANDBY_MODE`, `USER_FORCED_ENROLLMENT` | `DIAGNOSTIC_MODE` | (none) | (none) |
| **exit_diagnostic_mode** | `DIAGNOSTIC_MODE` | `OOB_MODE` | No Admin PIN is enrolled. | `(on_enter)` `on_enter_OOB_MODE` |
| | | `STANDBY_MODE` | Admin PIN is enrolled. | `(on_enter)` `on_enter_STANDBY_MODE` |
| | | `USER_FORCED_ENROLLMENT` | User Forced Enrollment is active. | (none) |
| **enroll_brute_force_counter** | `ADMIN_MODE` | `COUNTER_ENROLLMENT` | (none) | `(before)` `_brute_force_counter_enrollment`<br/>`(on_enter)` `on_enter_COUNTER_ENROLLMENT`|
| **enroll_unattended_auto_lock_counter** | `ADMIN_MODE` | `COUNTER_ENROLLMENT` | (none) | `(before)` `_unattended_auto_lock_enrollment`<br/>`(on_enter)` `on_enter_COUNTER_ENROLLMENT`|
| **enroll_min_pin_counter** | `ADMIN_MODE` | `COUNTER_ENROLLMENT` | (none) | `(before)` `_min_pin_enrollment`<br/>`(on_enter)` `on_enter_COUNTER_ENROLLMENT`|
| **enroll_counter** | `COUNTER_ENROLLMENT` | `ADMIN_MODE` | (none) | `(before)` `_counter_enrollment`<br/>`(on_enter)` `on_enter_ADMIN_MODE`|
| **timeout_enroll_counter** | `COUNTER_ENROLLMENT` | `ADMIN_MODE` | (none) | `(before)` `_timeout_counter_enrollment`<br/>`(on_enter)` `on_enter_ADMIN_MODE`|
| **exit_enroll_counter** | `COUNTER_ENROLLMENT` | `ADMIN_MODE` | (none) | `(before)` `_press_lock_button`<br/>`(on_enter)` `on_enter_ADMIN_MODE`|
| **enroll_recovery** | `ADMIN_MODE` | `PIN_ENROLLMENT` | (none) | `(before)` `_recovery_pin_enrollment`<br/>`(on_enter)` `on_enter_PIN_ENROLLMENT`|
| **enroll_self_destruct** | `ADMIN_MODE` | `PIN_ENROLLMENT` | (none) | `(before)` `_self_destruct_pin_enrollment`<br/>`(on_enter)` `on_enter_PIN_ENROLLMENT`|
| **enroll_pin** | `PIN_ENROLLMENT` | `ADMIN_MODE` | (none) | `(before)` `_pin_enrollment`<br/>`(on_enter)` `on_enter_ADMIN_MODE`|
| **timeout_enroll_pin** | `PIN_ENROLLMENT` | `ADMIN_MODE` | (none) | `(before)` `_timeout_pin_enrollment`<br/>`(on_enter)` `on_enter_ADMIN_MODE`|
| **exit_enroll_pin** | `PIN_ENROLLMENT` | `ADMIN_MODE` | (none) | `(before)` `_press_lock_button`<br/>`(on_enter)` `on_enter_ADMIN_MODE`|

### 4. Admin Mode Self-Transitions (Toggles)

While in `ADMIN_MODE`, several triggers are used to toggle device features. These transitions start and end in the `ADMIN_MODE` state.

| Trigger (Event) | Action / Callback | Description of Action |
| :--- | :--- | :--- |
| **toggle_basic_disk** | `_basic_disk_toggle` | Toggles basic disk mode and updates `DUT.basicDisk`. |
| **toggle_removable_media** | `_removable_media_toggle` | Toggles removable media mode. |
| **enable_led_Flicker** | `_led_flicker_enable` | Enables the LED flicker feature and updates `DUT.ledFlicker`. |
| **disable_led_Flicker** | `_led_flicker_disable` | Disables the LED flicker feature. |
| **delete_pins** | `_delete_pins_toggle` | Initiates the process to delete all enrolled User and Recovery PINs. |
| **toggle_lock_override** | `_lock_override_toggle` | Toggles the lock override feature. |
| **enable_provision_lock** | `_provision_lock_toggle` | Enables/disables the provision lock feature; fails if Self-Destruct is enabled. |
| **toggle_read_only** | `_read_only_toggle` | Puts the device into Read-Only mode. |
| **toggle_read_write** | `_read_write_toggle` | Puts the device into Read-Write mode. |
| **enable_self_destruct** | `_self_destruct_toggle` | Enables the self-destruct feature; fails if Provision Lock is enabled. |
| **toggle_user_forced_enrollment** | `_user_forced_enrollment_toggle`| Enables the User-Forced Enrollment mode; cannot be disabled via this toggle. |