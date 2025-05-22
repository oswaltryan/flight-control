# State Transition Diagram for Apricorn Device

**I. LIST OF STATES:**
*(List all unique, primary operational states. Think about what the device is "being" or "waiting for" at any given moment. Avoid listing actions as states here.)*

1.  `OFF`
2.  `SLEEP_MODE` (Low power, LEDs off, for battery-powered devices ONLY)
3.  `STARTUP_SELF_TEST` (Power-on self-test, hardware checks, for non-battery-powered devices ONLY)
4.  `OOB_MODE` (Out-of-Box, awaiting initial Admin PIN enrollment)
5.  `STANDBY_MODE` (Device configured, idle, locked, awaiting PIN for Admin/User/Recovery/Self-Destruct)
6.  `ADMIN_MODE` (Admin is authenticated and can perform configuration actions: enrolling pins, toggling features. Data partition likely NOT accessible for R/W here.)
7.  `ADMIN_MODE_UNLOCKED_DATA_ACCESS` (Admin PIN entered, data partition accessible for R/W or as per current R/O setting)
8.  `USER_MODE_UNLOCKED_DATA_ACCESS` (User PIN entered, data partition accessible for R/W or as per current R/O setting, according to user permissions)
9.  `SELF_DESTRUCT_UNLOCKED_DATA_ACCESS` (Self-Destruct PIN entered, data partition accessible for R/W)
10. `READ_ONLY_SESSION_ACTIVE` (A sub-state or flag indicating that the current unlocked session is read-only, could be entered from ADMIN_MODE_UNLOCKED_DATA_ACCESS or USER_MODE_UNLOCKED_DATA_ACCESS)
11. `DIAGNOSTIC_MODE` (Device version numbers and hardware IDs are displayed, after version display a keypad test is available)
12. `SELF_DESTRUCT_SEQUENCE_ACTIVE` (Self-destruct PIN entered, data being/has been wiped)
13. `USER_FORCED_ENROLLMENT` (Admin authorized, device now waiting for new User PIN sequence, appears the same as OOB Mode LEDs)
14. `BRUTE_FORCE_TIER1_LOCKOUT` (After N failed PIN attempts, temporary lockout, specific LED behavior)
15. `BRUTE_FORCE_TIER2_LOCKOUT` (Tier 1 was cleared successfully. After more failed PIN attempts, lockout data is wiped)
16. `PERMANENTLY_BRICKED` (Recovery failed, or other critical unrecoverable error, distinct LED behavior)
17. `FACTORY_RESETTING_IN_PROGRESS` (Transient state during reset process, specific LED behavior)
18. `AWAITING_PIN_ENROLLMENT_SEQUENCE` (Generic state for user to input a sequence of digits for a PIN.)
19. `AWAITING_COUNTER_VALUE_SETTING` (Generic state for user to input a sequence of digits for a counter.)
20. `AWAITING_PIN_LOGIN` (Generic state for user to enter PIN protected modes, NO DATA ACCESS)
21. `ERROR_MODE` (Generic state for errors)


**II. INITIAL STATE:**
*   BATTERY-POWERED DEVICE: `SLEEP MODE`
*   NON-BATTERY-POWERED DEVICE: `OFF`


**III. STATE DEFINITIONS & TRANSITIONS:**

*(For each state, define:*
*   *Description: A brief explanation of the state.*
*   *Entry Actions: What happens immediately upon entering this state (e.g., LED changes, checks performed, timers started).*
*   *Exit Actions: What happens immediately upon exiting this state (e.g., cleanup, timers stopped).*
*   *Internal Actions/Events Handled: Actions that can be performed *within* this state without causing a state change (e.g., an Admin in `ADMIN_MODE_CONFIGURING` toggles a feature).*
*   *Transitions Out:* List all possible events that can cause a transition *out* of this state.*)

---
**State: `OFF`**
*   **Description:** Device is powered down. No activity.
*   **Entry Actions:** (N/A if FSM starts here and assumes power off)
*   **Exit Actions:** None.
*   **Internal Actions/Events Handled:** None.
*   **Transitions Out:**
    1.  **Event:** `power_applied`
        *   **Condition(s):** Valid power source detected.
        *   **Action(s) during transition:** Log "Power applied to device."
        *   **Next State:** `STARTUP_SELF_TEST`

---
**State: `STARTUP_SELF_TEST`**
*   **Description:** Device is powering up, running power-on self-tests (POST), checking hardware integrity.
*   **Entry Actions:**
    *   Execute POST sequence (e.g., LED sequence Red->Green->Blue).
*   **Exit Actions:** None.
*   **Internal Actions/Events Handled:** None.
*   **Transitions Out:**
    1.  **Event:** `post_successful_oob_mode_detected`
        *   **Condition(s):** POST completed without errors AND hardware/firmware indicates "Out-of-Box" status.
        *   **Action(s) during transition:** Log "POST successful. Device is in OOB state."
        *   **Next State:** `OOB_MODE`
    2.  **Event:** `post_successful_standby_mode_detected`
        *   **Condition(s):** POST completed without errors AND hardware/firmware indicates "Standby" status.
        *   **Action(s) during transition:** Log "POST successful. Device is configured."
        *   **Next State:** `STANDBY_MODE`
    3.  **Event:** `post_successful_user_forced_enrollment_mode_detected`
        *   **Condition(s):** POST completed without errors AND hardware/firmware indicates "User-Forced Enrollment" status.
        *   **Action(s) during transition:** Log "POST successful. Device is in User-Forced Enrollment state."
        *   **Next State:** `USER_FORCED_ENROLLMENT`
    4.  **Event:** `post_successful_brute_force_tier1_detected`
        *   **Condition(s):** POST completed without errors AND hardware/firmware indicates "Brute Forced" status.
        *   **Action(s) during transition:** Log "POST successful. Device is in Brute Forced (Tier1) state."
        *   **Next State:** `BRUTE_FORCE_TIER1_LOCKOUT`
    5.  **Event:** `post_successful_brute_force_tier2_detected`
        *   **Condition(s):** POST completed without errors AND hardware/firmware indicates "Brute Forced" status.
        *   **Action(s) during transition:** Log "POST successful. Device is in Brute Forced (Tier2) state."
        *   **Next State:** `BRUTE_FORCE_TIER2_LOCKOUT`
    6.  **Event:** `post_unsuccessful_error_mode_detected`
        *   **Condition(s):** POST completed with errors AND hardware/firmware indicates "Error" status number (e.g., red LED blink count indicate error number, blue LED indicates end of error).
        *   **Action(s) during transition:** Log "POST unsuccessful. Device is in Error state."
        *   **Next State:** `ERROR_MODE`

---
**State: `OOB_MODE`**
*   **Description:** Out-of-Box Experience. Device requires initial Admin PIN enrollment. No data access.
*   **Entry Actions:**
    *   Set OOB-specific LED pattern (e.g., Solid Red, or specific blinking pattern indicating "needs setup").
    *   Log "Device in OOB_MODE. Awaiting initial Admin PIN enrollment."
*   **Exit Actions:** Clear OOB LED pattern.
*   **Internal Actions/Events Handled:** None.
*   **Transitions Out:**
    1.  **Event:** `admin_pin_enroll_procedure_initiated` (e.g., specific button press combo held for X seconds)
        *   **Condition(s):** Correct hardware interaction to start PIN enrollment.
        *   **Action(s) during transition:** Update LED to indicate "Admin PIN enrollment active". Log event.
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (with context: `is_initial_admin_enrollment=True`)
    2.  **Event:** `request_enter_diagnostic_mode`
        *   **Condition(s):** Correct key sequence for diagnostics from OOB is entered.
        *   **Action(s) during transition:** Log "Attempting to enter Diagnostic Mode from OOB."
        *   **Next State:** `DIAGNOSTIC_MODE_ACTIVE`
    3.  **Event:** `request_power_off`
        *   **Condition(s):** Power button held.
        *   **Action(s) during transition:** Log "Powering off from OOB_MODE."
        *   **Next State:** `OFF` (via a `SHUTTING_DOWN` transient state if needed)

---
**State: `STANDBY`**
*   **Description:** Device is configured, idle, and locked. Awaiting a valid PIN sequence for Admin, User, Recovery, or Self-Destruct. Default state after successful boot for a configured device or after locking.
*   **Entry Actions:**
    *   Set Standby LED pattern (e.g., Solid Red, or a "breathing" red).
    *   Reset internal PIN attempt counters for this standby session.
    *   Log "Device in STANDBY. Awaiting PIN."
*   **Exit Actions:** Clear Standby LED pattern.
*   **Internal Actions/Events Handled:** None.
*   **Transitions Out:**
    1.  **Event:** `pin_input_sequence_started` (e.g., first key pressed that's part of a PIN sequence)
        *   **Condition(s):** None.
        *   **Action(s) during transition:** Update LED to indicate "PIN entry in progress" (e.g., flicker per key press). Log event.
        *   **Next State:** `AWAITING_PIN_ENTRY`
    2.  **Event:** `request_enter_sleep_mode`
        *   **Condition(s):** No PIN entry in progress AND (e.g., inactivity timer expires OR specific "sleep" button press).
        *   **Action(s) during transition:** Log "Entering Sleep Mode from Standby."
        *   **Next State:** `SLEEP_MODE`
    3.  **Event:** `request_user_forced_enrollment_procedure`
        *   **Condition(s):** User Forced Enrollment feature is enabled in device config AND correct hardware interaction occurs.
        *   **Action(s) during transition:** Log "User Forced Enrollment procedure initiated from Standby." Update LED.
        *   **Next State:** `USER_FORCED_ENROLLMENT_AWAIT_ADMIN_AUTH`
    4.  **Event:** `request_enter_diagnostic_mode`
        *   **Condition(s):** Correct key sequence for diagnostics is entered.
        *   **Action(s) during transition:** Log "Attempting to enter Diagnostic Mode from Standby."
        *   **Next State:** `DIAGNOSTIC_MODE_ACTIVE`
    5.  **Event:** `request_power_off`
        *   **Condition(s):** Power button held.
        *   **Action(s) during transition:** Log "Powering off from STANDBY."
        *   **Next State:** `OFF`

---
**State: `AWAITING_PIN_ENTRY`**
*   **Description:** Device has received initial input indicating a PIN sequence is being entered. Actively waiting for subsequent digits and the confirmation/enter key.
*   **Entry Actions:**
    *   Start PIN entry timeout timer.
    *   LED feedback for active PIN entry (e.g., blinking green per digit, or specific color).
    *   Log "Awaiting full PIN sequence."
*   **Exit Actions:**
    *   Stop PIN entry timeout timer.
    *   Clear active PIN entry LED feedback.
*   **Internal Actions/Events Handled:**
    *   `digit_entered(digit)`: Append to buffer, update LED feedback. Reset timeout slightly.
    *   `clear_pin_entry_button_pressed`: Clear PIN buffer, reset LED. (Stays in `AWAITING_PIN_ENTRY`)
*   **Transitions Out:**
    1.  **Event:** `pin_sequence_submitted` (Payload: `buffered_pin_digits`)
        *   **Condition(s):** `is_pin_valid(buffered_pin_digits, type='admin')`
        *   **Action(s) during transition:** Log "Admin PIN correct." Reset brute force counter for this PIN type if applicable.
        *   **Next State:** `ADMIN_MODE_UNLOCKED_DATA_ACCESS` (or `ADMIN_MODE_CONFIGURING` if they are distinct entry points post-login)
    2.  **Event:** `pin_sequence_submitted` (Payload: `buffered_pin_digits`)
        *   **Condition(s):** `is_pin_valid(buffered_pin_digits, type='user')`
        *   **Action(s) during transition:** Log "User PIN correct." Reset brute force counter for this PIN type.
        *   **Next State:** `USER_MODE_UNLOCKED_DATA_ACCESS`
    3.  **Event:** `pin_sequence_submitted` (Payload: `buffered_pin_digits`)
        *   **Condition(s):** `is_pin_valid(buffered_pin_digits, type='recovery')` AND `is_provision_lock_active()` AND current state implies recovery is possible (e.g. from `BRICKED_AWAITING_ADMIN_RECOVERY_PIN` or a specific admin function).
        *   **Action(s) during transition:** Log "Recovery PIN correct."
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (with context `recovery_mode_active=True`)
    4.  **Event:** `pin_sequence_submitted` (Payload: `buffered_pin_digits`)
        *   **Condition(s):** `is_pin_valid(buffered_pin_digits, type='self_destruct')`
        *   **Action(s) during transition:** Log "Self-Destruct PIN validated."
        *   **Next State:** `SELF_DESTRUCT_SEQUENCE_ACTIVE`
    5.  **Event:** `pin_sequence_submitted` (Payload: `buffered_pin_digits`, `pin_type_attempted`)
        *   **Condition(s):** `NOT is_pin_valid(buffered_pin_digits, type=pin_type_attempted)` AND `get_brute_force_attempts(pin_type_attempted) >= MAX_ATTEMPTS_TIER1` AND `get_brute_force_attempts(pin_type_attempted) < MAX_ATTEMPTS_TIER2`
        *   **Action(s) during transition:** Log "Invalid PIN. Max attempts for Tier 1 reached." Increment global brute force counter. Update LED to Tier 1 lockout pattern.
        *   **Next State:** `BRUTE_FORCE_TIER1_LOCKOUT`
    6.  **Event:** `pin_sequence_submitted` (Payload: `buffered_pin_digits`, `pin_type_attempted`)
        *   **Condition(s):** `NOT is_pin_valid(buffered_pin_digits, type=pin_type_attempted)` AND `get_brute_force_attempts(pin_type_attempted) >= MAX_ATTEMPTS_TIER2`
        *   **Action(s) during transition:** Log "Invalid PIN. Max attempts for Tier 2 reached." Increment global brute force counter. Update LED to Tier 2 lockout pattern.
        *   **Next State:** `BRUTE_FORCE_TIER2_LOCKOUT` (This might then immediately check provision lock for next step)
    7.  **Event:** `pin_sequence_submitted` (Payload: `buffered_pin_digits`, `pin_type_attempted`)
        *   **Condition(s):** `NOT is_pin_valid(buffered_pin_digits, type=pin_type_attempted)` AND `get_brute_force_attempts(pin_type_attempted) < MAX_ATTEMPTS_TIER1`
        *   **Action(s) during transition:** Log "Invalid PIN. Attempts remaining..." Increment brute force counter for `pin_type_attempted`. Provide brief error LED (e.g., quick red flash).
        *   **Next State:** `STANDBY` (Returns to standby to allow re-attempt or different action)
    8.  **Event:** `pin_entry_timeout_expired`
        *   **Condition(s):** No valid PIN submitted within the timeout.
        *   **Action(s) during transition:** Log "PIN entry timed out."
        *   **Next State:** `STANDBY`
    9.  **Event:** `cancel_pin_entry_requested` (e.g. "Cancel" button pressed during PIN entry)
        *   **Condition(s):** None.
        *   **Action(s) during transition:** Log "PIN entry cancelled by user."
        *   **Next State:** `STANDBY`

---
**State: `ADMIN_MODE_CONFIGURING`**
*   **Description:** Admin is authenticated. Device is in a mode specifically for configuration changes (enrolling/deleting PINs, setting device feature toggles, initiating factory reset if allowed). Data partition may or may not be accessible depending on device design; assume NOT accessible for this specific config state unless explicitly transitioned to data access.
*   **Entry Actions:**
    *   Set Admin Configuration LED pattern (e.g., Blinking Green, or cycling colors).
    *   If `is_initial_admin_enrollment == True` (context from OOB):
        *   Guide Admin through initial PIN enrollment process (specific LED prompts, waiting for Phidget sequence).
        *   Log "Initial Admin PIN enrollment process started."
    *   Else (regular admin login to config mode):
        *   Log "Admin entered Configuration Mode."
    *   Load current device configuration settings for modification.
*   **Exit Actions:**
    *   Clear Admin Configuration LED pattern.
    *   If `is_initial_admin_enrollment == True` and PIN successfully set, save new Admin PIN checksum.
    *   Unset `is_initial_admin_enrollment` context.
    *   If any config changes were made and not yet committed, prompt/warn or auto-commit.
*   **Internal Actions/Events Handled (These are commands, not state changes):**
    *   `select_menu_item(item_name)`: e.g., "Enroll User PIN", "Toggle Features", "Change Admin PIN".
    *   `process_enroll_user_pin_sequence(phidget_keys)`
    *   `process_change_admin_pin_sequence(old_pin_keys, new_pin_keys)`
    *   `process_toggle_feature(feature_id, new_state)` (e.g. LED_FLICKER, READ_ONLY_DEFAULT)
    *   `process_set_brute_force_counter(value)`
    *   `process_set_min_pin_length(value)`
    *   (Each of these internal actions would have its own LED feedback and logic using `at` controller)
*   **Transitions Out:**
    1.  **Event:** `admin_config_exit_requested` (e.g., "Exit" menu option selected, or specific button press)
        *   **Condition(s):** If `is_initial_admin_enrollment == True`, then `new_admin_pin_successfully_enrolled == True`. (Cannot exit initial enrollment without setting a PIN).
        *   **Action(s) during transition:** Commit any pending configuration changes. Log "Exiting Admin Configuration Mode."
        *   **Next State:** `STANDBY`
    2.  **Event:** `request_admin_data_access` (e.g., "Access Drive" menu option)
        *   **Condition(s):** If `is_initial_admin_enrollment == True`, then `new_admin_pin_successfully_enrolled == True`.
        *   **Action(s) during transition:** Log "Admin requesting data access from config mode."
        *   **Next State:** `ADMIN_MODE_UNLOCKED_DATA_ACCESS`
    3.  **Event:** `initiate_factory_reset_from_admin_config` (e.g., "Factory Reset" menu option selected and confirmed)
        *   **Condition(s):** `NOT is_provision_lock_active()` (Device prevents reset if provision locked).
        *   **Action(s) during transition:** Log "Factory reset initiated by Admin from Configuration Mode."
        *   **Next State:** `FACTORY_RESETTING_IN_PROGRESS`
    4.  **Event:** `admin_session_timeout_expired`
        *   **Condition(s):** Admin inactivity timer in config mode expires.
        *   **Action(s) during transition:** Log "Admin configuration session timed out. Locking."
        *   **Next State:** `STANDBY`
    5.  **Event:** `request_power_off`
        *   **Next State:** `OFF`

---
**State: `ADMIN_MODE_UNLOCKED_DATA_ACCESS`**
*   **Description:** Admin is authenticated, and the data partition is accessible according to current device settings (R/W or R/O if toggled).
*   **Entry Actions:**
    *   Set Admin Data Access LED pattern (e.g., Solid Green for R/W, Solid Yellow for R/O session).
    *   Mount data partition (if not already mounted from a previous state like config).
    *   Log "Admin Unlocked for Data Access." If R/O, log that too.
*   **Exit Actions:**
    *   Unmount data partition (important for security before locking).
    *   Clear Admin Data Access LED pattern.
*   **Internal Actions/Events Handled:**
    *   `file_system_activity_detected`: (Handled by OS, FSM might just be aware).
    *   `request_toggle_current_session_to_read_only` (if not already R/O): Updates LED, sets internal flag.
    *   `request_toggle_current_session_to_read_write` (if in R/O session and allowed): Updates LED, sets internal flag.
*   **Transitions Out:**
    1.  **Event:** `lock_device_requested` (e.g., "Lock" button, USB eject, inactivity timeout different from config timeout)
        *   **Condition(s):** None.
        *   **Action(s) during transition:** Log "Locking device from Admin Data Access."
        *   **Next State:** `STANDBY`
    2.  **Event:** `request_enter_admin_configuration_mode` (e.g., specific key combo or menu if available while drive mounted)
        *   **Condition(s):** None.
        *   **Action(s) during transition:** Log "Admin switching to Configuration Mode from Data Access." (May unmount drive).
        *   **Next State:** `ADMIN_MODE_CONFIGURING`
    3.  **Event:** `request_enter_sleep_mode`
        *   **Condition(s):** None.
        *   **Action(s) during transition:** Log "Entering Sleep Mode from Admin Data Access."
        *   **Next State:** `SLEEP_MODE`
    4.  **Event:** `request_power_off`
        *   **Next State:** `OFF`

---
**State: `USER_MODE_UNLOCKED_DATA_ACCESS`**
*   **Description:** User is authenticated, data partition accessible as per their permissions and device R/O settings.
*   **Entry Actions:**
    *   Set User Data Access LED pattern (e.g., Solid Blue for R/W, Solid Cyan for R/O session).
    *   Mount data partition.
    *   Log "User Unlocked for Data Access." If R/O, log that too.
*   **Exit Actions:**
    *   Unmount data partition.
    *   Clear User Data Access LED pattern.
*   **Internal Actions/Events Handled:**
    *   `file_system_activity_detected`.
    *   `user_request_change_own_pin_sequence(phidget_keys_old_pin, phidget_keys_new_pin)`
    *   `user_request_enroll_self_destruct_pin_sequence(phidget_keys_sd_pin)`
*   **Transitions Out:**
    1.  **Event:** `lock_device_requested`
        *   **Next State:** `STANDBY`
    2.  **Event:** `request_enter_sleep_mode`
        *   **Next State:** `SLEEP_MODE`
    3.  **Event:** `request_power_off`
        *   **Next State:** `OFF`

---
**State: `READ_ONLY_SESSION_ACTIVE`**
*   **Description:** This might be better modeled as a boolean flag (`is_current_session_read_only`) within `ADMIN_MODE_UNLOCKED_DATA_ACCESS` and `USER_MODE_UNLOCKED_DATA_ACCESS` rather than a completely separate top-level state, unless the device has very distinct global behavior or LED patterns ONLY for read-only that override the Admin/User LED. If it's a flag, the Entry/Exit/Internal actions of the parent state would check this flag.
*   **If a separate state:**
    *   **Entry Actions:** Specific Read-Only LED (e.g., Solid Yellow regardless of Admin/User). Log "Session is now Read-Only."
    *   **Exit Actions:** Clear Read-Only LED. Log "Session no longer Read-Only."
    *   **Transitions Out:**
        1.  **Event:** `toggle_read_write_requested`
            *   **Condition(s):** User/Admin has permission to switch back.
            *   **Next State:** (The Admin or User unlocked data access state it came from).
        2.  `lock_device_requested` -> `STANDBY`
        3.  `request_enter_sleep_mode` -> `SLEEP_MODE`
        4.  `request_power_off` -> `OFF`

---
**State: `DIAGNOSTIC_MODE_ACTIVE`**
*   **Description:** Device is running internal diagnostics. Limited user interaction, specific LED feedback.
*   **Entry Actions:**
    *   Set Diagnostic LED pattern (e.g., Rapidly blinking Yellow/Orange).
    *   Log "Entered Diagnostic Mode."
    *   Initiate diagnostic routines (e.g., memory check, crypto engine test, storage health).
*   **Exit Actions:**
    *   Clear Diagnostic LED pattern.
    *   Log diagnostic results.
*   **Internal Actions/Events Handled:**
    *   `diagnostic_routine_step_complete(step_name, status)`: Update LED or log progress.
*   **Transitions Out:**
    1.  **Event:** `diagnostic_routines_completed_pass`
        *   **Condition(s):** All diagnostic tests passed.
        *   **Action(s) during transition:** Log "Diagnostics Passed."
        *   **Next State:** `STANDBY` (or `OOB_MODE` if entered from there and still OOB)
    2.  **Event:** `diagnostic_routines_completed_fail` (Payload: `error_codes`)
        *   **Condition(s):** One or more diagnostic tests failed.
        *   **Action(s) during transition:** Log "Diagnostics Failed. Error codes: {error_codes}."
        *   **Next State:** `BRICKED_AWAITING_ADMIN_RECOVERY_PIN` (if potentially fixable by admin/reset) or `PERMANENTLY_BRICKED` (if critical failure).
    3.  **Event:** `exit_diagnostic_mode_requested` (e.g., specific button press)
        *   **Condition(s):** None.
        *   **Action(s) during transition:** Abort ongoing diagnostics if stoppable. Log "Diagnostic mode exited by user."
        *   **Next State:** `STANDBY` (or `OOB_MODE` if entered from there)
    4.  **Event:** `request_power_off`
        *   **Next State:** `OFF`

---
**State: `SELF_DESTRUCT_SEQUENCE_ACTIVE`**
*   **Description:** Self-Destruct PIN has been validated. Device is actively wiping data or has completed wiping.
*   **Entry Actions:**
    *   Set Self-Destruct LED pattern (e.g., Rapidly blinking Red, or specific sequence).
    *   Log "SELF-DESTRUCT SEQUENCE ACTIVATED. Wiping data."
    *   Initiate irreversible data wipe procedures.
*   **Exit Actions:**
    *   Log "Data wipe complete (or process terminated if applicable)." Clear Self-Destruct LED pattern.
*   **Internal Actions/Events Handled:**
    *   `data_wipe_progress_update(percentage)`: (If device provides this).
*   **Transitions Out:**
    1.  **Event:** `data_wipe_completed`
        *   **Condition(s):** Wipe procedure finishes successfully.
        *   **Action(s) during transition:** Log "Self-Destruct data wipe completed. Device will reset to factory defaults."
        *   **Next State:** `FACTORY_RESETTING_IN_PROGRESS` (which will then lead to `OOB_MODE`)
    2.  **Event:** `data_wipe_failed_critical`
        *   **Condition(s):** Wipe procedure encounters an unrecoverable error.
        *   **Action(s) during transition:** Log "CRITICAL: Self-Destruct data wipe FAILED."
        *   **Next State:** `PERMANENTLY_BRICKED` (Device should be unusable and indicate severe error).
    3.  **Event:** `request_power_off` (This might be blocked by firmware during active wipe)
        *   **Condition(s):** Firmware allows power off during/after wipe initiation.
        *   **Next State:** `OFF`

---
**State: `USER_FORCED_ENROLLMENT_AWAIT_ADMIN_AUTH`**
*   **Description:** User Forced Enrollment (UFE) procedure has been initiated from Standby. Device is now waiting for a valid Admin PIN to authorize the enrollment of a new User PIN.
*   **Entry Actions:**
    *   Set UFE Admin Auth LED pattern (e.g., Alternating Red/Green, or specific prompt for Admin).
    *   Log "User Forced Enrollment: Awaiting Admin PIN for authorization."
    *   Start Admin Auth timeout timer for UFE.
*   **Exit Actions:**
    *   Clear UFE Admin Auth LED pattern.
    *   Stop Admin Auth timeout timer.
*   **Internal Actions/Events Handled:** (Similar to `AWAITING_PIN_ENTRY` but specifically for Admin PIN in this context)
    *   `admin_digit_entered_for_ufe_auth(digit)`
*   **Transitions Out:**
    1.  **Event:** `admin_pin_submitted_for_ufe_auth` (Payload: `admin_pin_digits`)
        *   **Condition(s):** `is_pin_valid(admin_pin_digits, type='admin')`
        *   **Action(s) during transition:** Log "Admin PIN validated for UFE. Proceeding to new User PIN enrollment."
        *   **Next State:** `USER_FORCED_ENROLLMENT_AWAIT_NEW_USER_PIN`
    2.  **Event:** `admin_pin_submitted_for_ufe_auth` (Payload: `admin_pin_digits`)
        *   **Condition(s):** `NOT is_pin_valid(admin_pin_digits, type='admin')`
        *   **Action(s) during transition:** Log "Invalid Admin PIN for UFE. Returning to Standby." Provide brief error LED. (Brute force for Admin PIN might apply here too).
        *   **Next State:** `STANDBY`
    3.  **Event:** `ufe_admin_auth_timeout_expired`
        *   **Condition(s):** No valid Admin PIN submitted within timeout.
        *   **Action(s) during transition:** Log "UFE Admin authorization timed out."
        *   **Next State:** `STANDBY`
    4.  **Event:** `cancel_ufe_procedure_requested`
        *   **Next State:** `STANDBY`
    5.  **Event:** `request_power_off`
        *   **Next State:** `OFF`

---
**State: `USER_FORCED_ENROLLMENT_AWAIT_NEW_USER_PIN`**
*   **Description:** Admin has authorized UFE. Device is now waiting for the sequence of Phidget key presses to define the new User PIN.
*   **Entry Actions:**
    *   Set UFE New User PIN Entry LED pattern (e.g., Blinking Blue, prompting for new User PIN).
    *   Log "User Forced Enrollment: Awaiting new User PIN entry."
    *   Start new User PIN entry timeout timer.
*   **Exit Actions:**
    *   Clear UFE New User PIN Entry LED pattern.
    *   Stop new User PIN entry timeout timer.
*   **Internal Actions/Events Handled:**
    *   `new_user_pin_digit_entered(digit)`
    *   `new_user_pin_confirmation_digit_entered(digit)` (if PIN needs to be entered twice)
*   **Transitions Out:**
    1.  **Event:** `new_user_pin_sequence_enrollment_complete` (Payload: `new_user_pin_digits`)
        *   **Condition(s):** New User PIN meets complexity requirements (length, etc.) AND (if confirmation used) PINs match.
        *   **Action(s) during transition:** Save new User PIN checksum. Log "New User PIN successfully enrolled via UFE."
        *   **Next State:** `STANDBY` (Device is now configured with the new User PIN and locked).
    2.  **Event:** `new_user_pin_sequence_enrollment_failed` (Payload: `reason` e.g., "mismatch", "too_short")
        *   **Condition(s):** New User PIN fails validation.
        *   **Action(s) during transition:** Log "New User PIN enrollment failed: {reason}." Provide error LED.
        *   **Next State:** `USER_FORCED_ENROLLMENT_AWAIT_NEW_USER_PIN` (Allow retry, possibly with limited attempts) OR `STANDBY` (if attempts exhausted or procedure cancelled).
    3.  **Event:** `ufe_new_user_pin_entry_timeout_expired`
        *   **Next State:** `STANDBY`
    4.  **Event:** `cancel_ufe_procedure_requested`
        *   **Next State:** `STANDBY`
    5.  **Event:** `request_power_off`
        *   **Next State:** `OFF`

---
**State: `BRUTE_FORCE_TIER1_LOCKOUT`**
*   **Description:** Device has entered a temporary lockout due to N successive invalid PIN attempts (for any single PIN type or globally, TBD). Limited functionality.
*   **Entry Actions:**
    *   Set Tier 1 Lockout LED pattern (e.g., Slow Pulsing Red).
    *   Log "BRUTE_FORCE_TIER1_LOCKOUT active. Device temporarily locked."
    *   Start Tier 1 lockout duration timer (e.g., 1 minute).
*   **Exit Actions:**
    *   Clear Tier 1 Lockout LED pattern.
    *   Stop Tier 1 lockout timer.
*   **Internal Actions/Events Handled:**
    *   Most key presses ignored, except perhaps a specific sequence to show remaining lockout time if supported.
*   **Transitions Out:**
    1.  **Event:** `tier1_lockout_duration_expired`
        *   **Condition(s):** Timer completes.
        *   **Action(s) during transition:** Log "Tier 1 lockout expired. Returning to Standby." (Brute force counters might be partially reset or retain state).
        *   **Next State:** `STANDBY`
    2.  **Event:** `power_cycle_detected` (If power cycle bypasses Tier 1 - depends on device non-volatile memory for BF count)
        *   **Condition(s):** Device is power cycled.
        *   **Action(s) during transition:** Log "Power cycle during Tier 1 lockout."
        *   **Next State:** `INITIALIZING` (which then might re-evaluate BF counters if they persist)
    3.  **Event:** `request_power_off`
        *   **Next State:** `OFF`

---
**State: `BRUTE_FORCE_TIER2_LOCKOUT`**
*   **Description:** Device has entered a more severe lockout due to continued invalid PIN attempts after Tier 1, or a higher threshold reached. May require longer timeout or Admin intervention.
*   **Entry Actions:**
    *   Set Tier 2 Lockout LED pattern (e.g., Rapid Pulsing Red, or Solid Red + Orange).
    *   Log "BRUTE_FORCE_TIER2_LOCKOUT active."
    *   Start Tier 2 lockout duration timer (e.g., 5 minutes, or indefinite until specific action).
*   **Exit Actions:**
    *   Clear Tier 2 Lockout LED pattern.
    *   Stop Tier 2 lockout timer.
*   **Internal Actions/Events Handled:**
    *   Key presses likely ignored.
*   **Transitions Out:**
    1.  **Event:** `tier2_lockout_resolved_by_timeout_or_action` (This state's exit logic is complex based on Provision Lock)
        *   **Condition(s):** `NOT is_provision_lock_active()` AND (Tier 2 timer expires OR specific non-PIN reset action if available).
        *   **Action(s) during transition:** Log "Tier 2 lockout resolved (no provision lock). Initiating factory reset."
        *   **Next State:** `FACTORY_RESETTING_IN_PROGRESS` (Device forces a reset if not provision locked)
    2.  **Event:** `tier2_lockout_provision_lock_active_transition`
        *   **Condition(s):** `is_provision_lock_active()` (This might be an immediate check on entering Tier 2, making this transition automatic if PL is on).
        *   **Action(s) during transition:** Log "Tier 2 lockout with Provision Lock active. Awaiting Admin Recovery PIN."
        *   **Next State:** `BRICKED_AWAITING_ADMIN_RECOVERY_PIN`
    3.  **Event:** `request_power_off`
        *   **Next State:** `OFF`

---
**State: `BRICKED_AWAITING_ADMIN_RECOVERY_PIN`**
*   **Description:** Device is in a "bricked" state due to severe brute force with Provision Lock enabled. Only a valid Admin Recovery PIN can potentially reset it.
*   **Entry Actions:**
    *   Set Bricked/Admin Recovery LED pattern (e.g., Solid Orange, or specific "SOS" like pattern).
    *   Log "DEVICE BRICKED (Provision Lock). Awaiting Admin Recovery PIN."
    *   Initialize Admin Recovery PIN attempt counter.
*   **Exit Actions:**
    *   Clear Bricked/Admin Recovery LED pattern.
*   **Internal Actions/Events Handled:** (Awaiting Admin Recovery PIN input)
    *   `admin_recovery_pin_digit_entered(digit)`
*   **Transitions Out:**
    1.  **Event:** `admin_recovery_pin_sequence_submitted` (Payload: `recovery_pin_digits`)
        *   **Condition(s):** `is_pin_valid(recovery_pin_digits, type='admin_recovery')`
        *   **Action(s) during transition:** Log "Admin Recovery PIN validated. Device will be factory reset."
        *   **Next State:** `FACTORY_RESETTING_IN_PROGRESS`
    2.  **Event:** `admin_recovery_pin_sequence_submitted` (Payload: `recovery_pin_digits`)
        *   **Condition(s):** `NOT is_pin_valid(recovery_pin_digits, type='admin_recovery')` AND `get_admin_recovery_attempts() >= MAX_ADMIN_RECOVERY_ATTEMPTS`
        *   **Action(s) during transition:** Log "Max Admin Recovery PIN attempts failed. Device permanently bricked."
        *   **Next State:** `PERMANENTLY_BRICKED`
    3.  **Event:** `admin_recovery_pin_sequence_submitted` (Payload: `recovery_pin_digits`)
        *   **Condition(s):** `NOT is_pin_valid(recovery_pin_digits, type='admin_recovery')` AND `get_admin_recovery_attempts() < MAX_ADMIN_RECOVERY_ATTEMPTS`
        *   **Action(s) during transition:** Log "Invalid Admin Recovery PIN. Attempts remaining..." Increment recovery attempt counter. Provide brief error LED.
        *   **Next State:** `BRICKED_AWAITING_ADMIN_RECOVERY_PIN` (Stays in state for more attempts)
    4.  **Event:** `request_power_off`
        *   **Next State:** `OFF` (State of bricking should persist across power cycles)

---
**State: `PERMANENTLY_BRICKED`**
*   **Description:** Device is unrecoverable due to critical POST failure, failed Admin Recovery, or failed Self-Destruct wipe. No user/admin actions possible.
*   **Entry Actions:**
    *   Set Permanent Bricked LED pattern (e.g., All LEDs solid RED, or specific non-blinking error pattern).
    *   Log "DEVICE PERMANENTLY BRICKED. No further operations possible."
    *   Firmware should disable most/all interfaces.
*   **Exit Actions:** (Likely none, as it shouldn't exit this state except by power off)
*   **Internal Actions/Events Handled:** None. All inputs ignored.
*   **Transitions Out:**
    1.  **Event:** `request_power_off`
        *   **Next State:** `OFF` (On next power on, it should re-enter `INITIALIZING` and likely detect the bricked status again, returning here or to a specific POST failure state that leads here).

---
**State: `FACTORY_RESETTING_IN_PROGRESS`**
*   **Description:** Device is actively performing a factory reset (wiping config, user data, PINs). This is a transient state.
*   **Entry Actions:**
    *   Set Factory Reset LED pattern (e.g., Cycling through all LED colors, or wiping animation).
    *   Log "Factory reset in progress. Wiping all data and settings."
    *   Initiate firmware routine for factory reset.
*   **Exit Actions:**
    *   Clear Factory Reset LED pattern.
*   **Internal Actions/Events Handled:**
    *   `factory_reset_progress_update(percentage)` (If available)
*   **Transitions Out:**
    1.  **Event:** `factory_reset_completed_successfully`
        *   **Condition(s):** Firmware confirms reset is complete.
        *   **Action(s) during transition:** Log "Factory reset completed. Device is now in OOB state."
        *   **Next State:** `OOB_MODE`
    2.  **Event:** `factory_reset_failed_critical`
        *   **Condition(s):** Firmware reports an error during the reset process.
        *   **Action(s) during transition:** Log "CRITICAL: Factory reset FAILED."
        *   **Next State:** `PERMANENTLY_BRICKED` (A failed reset is very bad).
    3.  **Event:** `request_power_off` (May be blocked by firmware during active reset)
        *   **Next State:** `OFF`

---
**State: `SLEEP_MODE`**
*   **Description:** Device is in a low-power state. Quick resume to `STANDBY` is expected. LEDs are typically off.
*   **Entry Actions:**
    *   Turn off all primary LEDs (or set a very dim sleep indicator if applicable).
    *   Log "Entering Sleep Mode."
    *   Reduce power to non-essential components.
*   **Exit Actions:**
    *   Log "Exiting Sleep Mode."
    *   Restore power to components needed for Standby.
*   **Internal Actions/Events Handled:** None.
*   **Transitions Out:**
    1.  **Event:** `wake_up_stimulus_detected` (e.g., any key press, USB bus activity if configured to wake on USB)
        *   **Condition(s):** None.
        *   **Action(s) during transition:** Log "Wake-up stimulus detected."
        *   **Next State:** `STANDBY` (Should not re-run full POST unless it's a "deep sleep" equivalent to power off).
    2.  **Event:** `request_power_off` (e.g. holding power button even in sleep)
        *   **Next State:** `OFF`

---

**IV. REUSABLE CONDITIONS / ACTIONS (Functions/Methods the FSM will need):**
*(List helper functions that will be used in conditions or actions. This helps identify what methods your FSM class will need, often interacting with `at` controller via your `automation_toolkit`)*

*   **PIN Validation & Handling:**
    *   `is_pin_valid(pin_digits_sequence, expected_pin_type)` -> bool (types: 'admin', 'user', 'recovery_admin', 'self_destruct')
    *   `get_pin_attempt_count(pin_type_or_global)` -> int
    *   `increment_pin_attempt_count(pin_type_or_global)`
    *   `reset_pin_attempt_count(pin_type_or_global)`
    *   `get_max_pin_attempts(tier_level)` -> int (e.g., tier1, tier2, recovery_admin_attempts)
    *   `check_pin_complexity(pin_digits_sequence)` -> bool
*   **Device Configuration & Status:**
    *   `is_provision_lock_active()` -> bool
    *   `is_oob_status()` -> bool (checks if Admin PIN is set/device is virgin)
    *   `is_user_forced_enrollment_feature_enabled()` -> bool
    *   `get_device_feature_toggle_state(feature_id)` -> bool
    *   `set_device_feature_toggle_state(feature_id, new_state)`
    *   `commit_pending_config_changes()`
    *   `is_initial_admin_enrollment_context()` -> bool (flag set when entering config from OOB)
    *   `set_initial_admin_enrollment_context(boolean)`
    *   `is_current_session_read_only()` -> bool (flag for current unlocked session)
    *   `set_current_session_read_only(boolean)`
*   **LED Management (Wrappers around `at` controller calls):**
    *   `set_led_pattern(pattern_name_or_definition)` (e.g., "STANDBY", "OOB", "ADMIN_CONFIG", "ERROR_TIER1")
    *   `clear_all_leds()`
*   **Hardware Interaction (Wrappers around `at`):**
    *   `initiate_phidget_pin_entry_sequence(prompt_message_or_led)` -> buffered_pin_digits_or_timeout
    *   `execute_phidget_sequence_for_action(action_name, payload)`
    *   `mount_data_partition()`
    *   `unmount_data_partition()`
    *   `initiate_device_self_destruct_wipe()`
    *   `initiate_device_factory_reset()`
    *   `run_diagnostic_routines()` -> pass/fail_with_codes
    *   `power_down_components_for_sleep()`
    *   `power_up_components_from_sleep()`
*   **Logging:**
    *   `log_fsm_event(message, level='info')`
*   **Timers (May need a simple timer mechanism or use `transitions` built-in state timeouts):**
    *   `start_timer(timer_name, duration_seconds, timeout_event_to_trigger)`
    *   `stop_timer(timer_name)`

---

This Markdown provides a comprehensive template. The next step is for you to go through it meticulously, align it with your Apricorn device's exact behavior (referencing its PDF manual for sequences, LED patterns, and specific rules), and fill in all the blanks. Pay close attention to:
*   **Correct LED patterns** for each state/action.
*   **Specific Phidget key sequences** for events.
*   **Conditions** that are truly enforced by the device.
*   **Exact sequence of events** for complex operations like Brute Force or User Forced Enrollment.

Once this diagram is solid, translating it into `python-transitions` code will be much more straightforward and less error-prone.