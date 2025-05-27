# Comprehensive State Transition Diagram for Automating Apricorn Device (Automation Perspective)

This document outlines the states and transitions from the perspective of an automation system controlling and verifying an Apricorn-like secure USB device. It is based on the features described in `device_markdown_map.md`.

**I. LIST OF STATES (Automation Perspective):**

**Core States:**
1.  `DEVICE_OFF`: Device unpowered.
2.  `POWERING_ON`: Power applied, awaiting POST.
3.  `VERIFYING_POST`: Observing POST LED sequence.
4.  `DEVICE_IN_STANDBY_MODE`: Locked, configured, awaiting PIN.
5.  `LOCKING_DEVICE`: Lock command issued, awaiting Standby confirmation.
6.  `POWERING_OFF`: Power-off command issued, awaiting LED confirmation.
7.  `AUTOMATION_ERROR_STATE`: Automation encountered an unrecoverable error.

**OOB & Initial Setup States:**
8.  `DEVICE_IN_OOB_MODE`: POST successful, device in Out-of-Box state.
9.  `AWAITING_OOB_ADMIN_PIN_ENROLL_START`: In OOB, initiating Admin PIN enrollment.
10. `OOB_ADMIN_PIN_ENROLLING`: Inputting new Admin PIN in OOB.

**PIN Entry & Unlock States:**
11. `AWAITING_PIN_INPUT`: Keypad active, automation inputting a PIN. (Generic for User, Admin, SD, Recovery).
12. `AWAITING_UNLOCK_CONFIRMATION`: PIN submitted, observing LEDs/USB for unlock outcome.

**Unlocked States (Data Access):**
13. `USER_MODE_UNLOCKED`: User PIN accepted, data accessible.
14. `ADMIN_MODE_UNLOCKED_DATA`: Admin PIN accepted for data access.
15. `SELF_DESTRUCT_MODE_UNLOCKED_DATA`: Self-Destruct PIN accepted, data accessible (prior to wipe completion if device allows temporary access).

**Admin Configuration Mode States:**
16. `AWAITING_ADMIN_CONFIG_MODE_ENTRY`: Admin PIN for *configuration* submitted.
17. `ADMIN_MODE_CONFIGURING`: In Admin config mode, awaiting action selection.
18. `ADMIN_MODE_NAVIGATING_MENU`: Sending key sequences to navigate Admin menus.
19. `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL`: Admin sub-op requires new PIN entry (e.g. Enroll User, Change Admin).
20. `ADMIN_MODE_ENTERING_NEW_PIN`: Inputting a new PIN (User, Admin, SD, Recovery) during Admin config.
21. `ADMIN_MODE_AWAITING_NEW_PIN_CONFIRMATION`: Inputting the new PIN a second time for confirmation.
22. `ADMIN_MODE_AWAITING_COUNTER_VALUE_INPUT`: Admin sub-op requires numeric input (e.g. Brute Force Counter, Min PIN Length).
23. `ADMIN_MODE_ENTERING_COUNTER_VALUE`: Inputting digits for a counter.
24. `ADMIN_MODE_TOGGLING_FEATURE`: Sending sequence to toggle a feature, awaiting feedback.
25. `ADMIN_MODE_INITIATING_USER_RESET`: Confirming User Reset (Factory Default) from Admin Mode.

**User Forced Enrollment (UFE) States:**
26. `AWAITING_UFE_START_CONFIRMATION`: UFE hardware sequence sent from Standby.
27. `UFE_AWAITING_ADMIN_PIN_AUTH`: UFE mode active, awaiting Admin PIN.
28. `UFE_AWAITING_NEW_USER_PIN_ENROLL`: UFE Admin Auth OK, awaiting new User PIN.

**Brute Force & Recovery States:**
29. `BRUTE_FORCE_TIER1_LOCKOUT_DETECTED`: Device showing Tier 1 Brute Force lockout LEDs.
30. `BRUTE_FORCE_TIER2_LOCKOUT_DETECTED`: Device showing Tier 2 Brute Force lockout LEDs.
31. `DEVICE_BRICKED_AWAITING_ADMIN_RECOVERY_PIN`: Bricked by BF+ProvisionLock, awaiting Admin Recovery PIN.
32. `DEVICE_PERMANENTLY_BRICKED_DETECTED`: LEDs indicate permanent, unrecoverable bricked state.

**Reset & Self-Destruct States:**
33. `INITIATING_FACTORY_RESET`: Factory Reset command issued, awaiting process.
34. `FACTORY_RESET_IN_PROGRESS`: Observing Factory Reset LED pattern.
35. `SELF_DESTRUCT_SEQUENCE_ACTIVE_WIPING`: Self-Destruct PIN accepted, observing wipe/reset.

**Diagnostic Mode States:**
36. `AWAITING_DIAGNOSTIC_MODE_ENTRY`: Diagnostic mode entry sequence sent.
37. `DIAGNOSTIC_MODE_DISPLAYING_INFO`: Observing version/ID display.
38. `DIAGNOSTIC_MODE_KEYPAD_TEST_ACTIVE`: Keypad test active within Diagnostics.

**Sleep Mode (If applicable to automation):**
39. `DEVICE_IN_SLEEP_MODE`: Device detected/assumed in low-power sleep.
40. `AWAKENING_FROM_SLEEP`: Wake-up stimulus sent/detected.

**II. INITIAL STATE (Automation Perspective):**
*   `DEVICE_OFF`

**III. STATE DEFINITIONS & TRANSITIONS (Automation Perspective):**

---
**State: `DEVICE_OFF`**
*   **Description:** Automation considers the device to be unpowered.
*   **Entry Actions (by Automation):**
    *   `at.off("usb3")`, `at.off("connect")` (to ensure power cut).
    *   `at.confirm_led_solid(LEDs['ALL_OFF'], minimum=2, timeout=5)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `initiate_power_on`
        *   **Action(s) during transition:** Log "Requesting device power on."
        *   **Next State:** `POWERING_ON`

---
**State: `POWERING_ON`**
*   **Description:** Automation has applied power and is waiting for the device to begin its POST sequence.
*   **Entry Actions (by Automation):**
    *   `at.on("usb3")`
    *   `at.on("connect")`
    *   Start a short timer (e.g., 1-2 seconds) for POST to begin.
*   **Exit Actions:** Stop POST initiation timer.
*   **Transitions Out:**
    1.  **Event (Timer Expires or Initial LED Activity):** `proceed_to_post_verification`
        *   **Action(s) during transition:** Log "Proceeding to verify POST sequence."
        *   **Next State:** `VERIFYING_POST`
    2.  **Event (Timeout with no LED activity):** `power_on_timeout_no_post`
        *   **Action(s) during transition:** Log "ERROR: Device powered on, but no POST activity detected within timeout."
        *   **Next State:** `AUTOMATION_ERROR_STATE` (or a specific `ERROR_NO_POST`)

---
**State: `VERIFYING_POST`**
*   **Description:** Automation is actively checking for the defined POST LED pattern.
*   **Entry Actions (by Automation):**
    *   `is_post_ok = at.confirm_led_pattern(LEDs['STARTUP'], clear_buffer=True)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `post_sequence_successful_oob_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_solid(LEDs['OOB_MODE_PATTERN'] or LEDs['STANDBY_MODE'], minimum=1, timeout=3, clear_buffer=False)` indicates OOB. (Using `clear_buffer=False` as POST just finished).
        *   **Action(s) during transition:** Log "POST sequence verified successfully. Device appears to be in OOB mode."
        *   **Next State:** `DEVICE_IN_OOB_MODE`
    2.  **Event:** `post_sequence_successful_standby_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_solid(LEDs['STANDBY_MODE'], minimum=1, timeout=3, clear_buffer=False)` indicates Standby.
        *   **Action(s) during transition:** Log "POST sequence verified successfully. Device appears to be in Standby mode."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`
    3.  **Event:** `post_sequence_successful_ufe_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_solid(LEDs['UFE_AWAIT_ADMIN_AUTH_PATTERN'], minimum=1, timeout=3, clear_buffer=False)` indicates UFE mode.
        *   **Action(s) during transition:** Log "POST sequence verified successfully. Device appears to be in User Forced Enrollment mode."
        *   **Next State:** `UFE_AWAITING_ADMIN_PIN_AUTH`
    4.  **Event:** `post_sequence_successful_brute_force_tier1_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER1_PATTERN'], clear_buffer=False)`
        *   **Action(s) during transition:** Log "POST sequence verified successfully. Device appears to be in Brute Force Tier 1 Lockout."
        *   **Next State:** `BRUTE_FORCE_TIER1_LOCKOUT_DETECTED`
    5.  **Event:** `post_sequence_successful_brute_force_tier2_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER2_PATTERN'], clear_buffer=False)`
        *   **Action(s) during transition:** Log "POST sequence verified successfully. Device appears to be in Brute Force Tier 2 Lockout."
        *   **Next State:** `BRUTE_FORCE_TIER2_LOCKOUT_DETECTED`
    6.  **Event:** `post_sequence_failed_or_unknown_state`
        *   **Condition(s):** `is_post_ok == False` OR no known state pattern detected after POST.
        *   **Action(s) during transition:** Log "ERROR: POST LED sequence verification failed or resulted in an unknown state."
        *   **Next State:** `AUTOMATION_ERROR_STATE`

---
**State: `DEVICE_IN_OOB_MODE`**
*   **Description:** Automation has confirmed the device is in Out-of-Box mode.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_solid(LEDs['OOB_MODE_PATTERN'] or LEDs['STANDBY_MODE'], minimum=2, timeout=5, clear_buffer=True)` (Assuming OOB shows solid Red like Standby initially, or a specific OOB pattern). `clear_buffer=True` as we expect a stable state now.
    *   Log "Device confirmed in OOB_MODE."
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `initiate_oob_admin_pin_enrollment`
        *   **Action(s) during transition:** Log "Initiating OOB Admin PIN enrollment."
        *   **Next State:** `AWAITING_OOB_ADMIN_PIN_ENROLL_START`
    2.  **Event (Automation Trigger):** `request_diagnostic_mode_from_oob`
        *   **Action(s) during transition:** `at.sequence(config.OOB_DIAGNOSTIC_MODE_KEYS)`
        *   **Next State:** `AWAITING_DIAGNOSTIC_MODE_ENTRY`
    3.  **Event (Automation Trigger):** `request_user_reset_from_oob`
        *   **Condition(s):** `not at.is_provision_lock_enabled()` (Hypothetical check, OOB usually allows reset).
        *   **Action(s) during transition:** Log "Requesting User Reset (Factory Default) from OOB mode."
        *   **Next State:** `INITIATING_FACTORY_RESET` (Payload: `source_state='OOB_MODE'`)
    4.  **Event (Automation Trigger):** `request_power_off_from_oob`
        *   **Action(s) during transition:** Log "Requesting power off from OOB mode."
        *   **Next State:** `POWERING_OFF`

---
**State: `AWAITING_OOB_ADMIN_PIN_ENROLL_START`**
*   **Description:** Automation is ready to send the key sequence to start Admin PIN enrollment from OOB.
*   **Entry Actions (by Automation):**
    *   `at.sequence(config.OOB_ADMIN_ENROLL_START_KEYS)` (e.g., Hold Unlock + 1 for X sec)
    *   `is_enroll_prompt_ok = at.await_led_state(LEDs['ADMIN_NEW_PIN_ENTRY_PROMPT'], timeout=5, clear_buffer=False)` (Device indicating it's ready for new PIN).
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `oob_admin_enroll_prompt_confirmed`
        *   **Condition(s):** `is_enroll_prompt_ok == True`.
        *   **Action(s) during transition:** Log "OOB Admin PIN enrollment prompt confirmed."
        *   **Next State:** `OOB_ADMIN_PIN_ENROLLING` (Payload: `new_admin_pin`)
    2.  **Event:** `oob_admin_enroll_prompt_failed`
        *   **Condition(s):** `is_enroll_prompt_ok == False`.
        *   **Action(s) during transition:** Log "ERROR: Failed to confirm OOB Admin PIN enrollment prompt."
        *   **Next State:** `AUTOMATION_ERROR_STATE`

---
**State: `OOB_ADMIN_PIN_ENROLLING`**
*   **Description:** Automation is inputting the new Admin PIN and confirmation during OOB setup.
*   **Entry Actions (by Automation, using `event_data.kwargs['new_admin_pin']`):**
    *   `new_pin_to_enroll = event_data.kwargs['new_admin_pin']`
    *   `at.sequence(new_pin_to_enroll)` (Assuming `new_admin_pin` is the first entry sequence)
    *   `is_confirm_prompt_ok = at.await_led_state(LEDs['ADMIN_NEW_PIN_CONFIRM_PROMPT'], timeout=5, clear_buffer=False)`
    *   `is_enroll_success = False`
    *   If `is_confirm_prompt_ok`:
        *   `at.sequence(new_pin_to_enroll)` (Assuming PIN is entered again for confirmation)
        *   `is_enroll_success = at.await_led_state(LEDs['ACCEPT_PATTERN'], timeout=10, clear_buffer=False)`
        *   If `is_enroll_success`:
             `is_enroll_success = at.await_led_state(LEDs['ADMIN_MODE'] or LEDs['STANDBY_MODE'], timeout=5, clear_buffer=False)` (Confirm final state after accept)
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `oob_admin_pin_enroll_successful`
        *   **Condition(s):** `is_enroll_success == True`.
        *   **Action(s) during transition:** Log "OOB Admin PIN enrolled successfully."
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Device often goes to Admin Mode after initial Admin PIN set) or `DEVICE_IN_STANDBY_MODE`.
    2.  **Event:** `oob_admin_pin_enroll_failed`
        *   **Condition(s):** `is_enroll_success == False` or intermediate prompt failed.
        *   **Action(s) during transition:** Log "ERROR: OOB Admin PIN enrollment failed."
        *   **Next State:** `AUTOMATION_ERROR_STATE`

---
**State: `DEVICE_IN_STANDBY_MODE`**
*   **Description:** Automation has confirmed the device is in Standby mode (locked, configured).
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_solid(LEDs['STANDBY_MODE'], minimum=2, timeout=5, clear_buffer=True)`
    *   Log "Device confirmed in STANDBY_MODE."
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `initiate_pin_unlock` (Payload: `pin_sequence`, `pin_type` \['user', 'admin_data', 'self_destruct', 'recovery'\], `expected_unlock_success_pattern`, `target_successful_state`)
        *   **Action(s) during transition:** Log "Initiating PIN unlock of type: {payload['pin_type']}."
        *   **Next State:** `AWAITING_PIN_INPUT`
    2.  **Event (Automation Trigger):** `initiate_admin_config_mode_entry` (Payload: `admin_pin_sequence`)
        *   **Action(s) during transition:** Log "Attempting to enter Admin Configuration Mode."
        *   **Next State:** `AWAITING_ADMIN_CONFIG_MODE_ENTRY`
    3.  **Event (Automation Trigger):** `initiate_user_forced_enrollment_start`
        *   **Action(s) during transition:** `at.sequence(config.UFE_START_KEYS_FROM_STANDBY)`
        *   Log "Attempting to initiate User Forced Enrollment."
        *   **Next State:** `AWAITING_UFE_START_CONFIRMATION`
    4.  **Event (Automation Trigger):** `request_diagnostic_mode_from_standby`
        *   **Action(s) during transition:** `at.sequence(config.STANDBY_DIAGNOSTIC_MODE_KEYS)`
        *   Log "Attempting to enter Diagnostic Mode from Standby."
        *   **Next State:** `AWAITING_DIAGNOSTIC_MODE_ENTRY`
    5.  **Event (Automation Trigger):** `request_user_reset_from_standby`
        *   **Condition(s):** `not at.is_provision_lock_enabled()`.
        *   **Action(s) during transition:** `at.sequence(config.STANDBY_USER_RESET_KEYS)` (if direct key sequence exists, otherwise needs Admin)
        *   Log "Attempting User Reset (Factory Default) from Standby."
        *   **Next State:** `INITIATING_FACTORY_RESET` (Payload: `source_state='STANDBY_MODE'`)
    6.  **Event (Automation Trigger):** `request_power_off_from_standby`
        *   **Action(s) during transition:** Log "Requesting power off from Standby mode."
        *   **Next State:** `POWERING_OFF`
    7.  **Event (Automation Trigger, if applicable):** `request_sleep_mode`
        *   **Action(s) during transition:** `at.sequence(config.SLEEP_MODE_KEYS)` (if applicable)
        *   Log "Requesting device to enter Sleep Mode."
        *   **Next State:** `DEVICE_IN_SLEEP_MODE` (after confirmation)

---
**State: `AWAITING_PIN_INPUT`**
*   **Description:** Generic state for automation inputting any PIN.
*   **Entry Actions (Payload: `pin_sequence`, `pin_type`, `expected_unlock_success_pattern`, `target_successful_state`):**
    *   `self.current_pin_type = event_data.kwargs['pin_type']`
    *   `self.current_expected_pattern = event_data.kwargs['expected_unlock_success_pattern']`
    *   `self.current_target_state = event_data.kwargs['target_successful_state']`
    *   Log f"Inputting PIN for type: {self.current_pin_type}."
    *   `at.sequence(event_data.kwargs['pin_sequence'])`
    *   Log "PIN sequence submitted."
    *   `self.proceed_to_unlock_confirmation(expected_pattern=self.current_expected_pattern, target_state=self.current_target_state, attempted_pin_type=self.current_pin_type)`
*   **Exit Actions:** None.
*   **Transitions Out:** (Handled by `proceed_to_unlock_confirmation` trigger)
    1.  **Event (Internal):** `proceed_to_unlock_confirmation` -> `AWAITING_UNLOCK_CONFIRMATION`

---
**State: `AWAITING_UNLOCK_CONFIRMATION`**
*   **Description:** Automation is observing LEDs/USB for confirmation of PIN acceptance.
*   **Entry Actions (by Automation, using `event_data.kwargs`):**
    *   `expected_pattern = event_data.kwargs['expected_pattern']`
    *   `pin_type = event_data.kwargs['attempted_pin_type']`
    *   `target_state_on_success = event_data.kwargs['target_state']`
    *   Log f"Awaiting unlock confirmation for PIN type: {pin_type}."
    *   `is_unlock_pattern_ok = at.await_and_confirm_led_pattern(expected_pattern, timeout=15, clear_buffer=False)`
    *   `is_reject_pattern_ok = False`
    *   `did_brute_force_tier1_trigger = False`
    *   `did_brute_force_tier2_trigger = False`

    *   If not `is_unlock_pattern_ok`:
        *   `is_reject_pattern_ok = at.confirm_led_pattern(LEDs['REJECT_PATTERN'], clear_buffer=False)`
        *   If not `is_reject_pattern_ok`: # Check for brute force only if not explicit reject or success
            *   `did_brute_force_tier1_trigger = at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER1_PATTERN'], clear_buffer=False)`
            *   If not `did_brute_force_tier1_trigger`:
                *   `did_brute_force_tier2_trigger = at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER2_PATTERN'], clear_buffer=False)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `unlock_successful`
        *   **Condition(s):** `is_unlock_pattern_ok == True`.
        *   **Action(s) during transition:** Log f"Unlock successful for PIN type {pin_type} (pattern confirmed)."
        *   **Next State:** `target_state_on_success`
    2.  **Event:** `unlock_pin_rejected`
        *   **Condition(s):** `is_reject_pattern_ok == True`.
        *   **Action(s) during transition:** Log f"PIN rejected for type {pin_type}."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE` (or `DEVICE_BRICKED_AWAITING_ADMIN_RECOVERY_PIN` if `pin_type` was 'admin_recovery_from_bricked' and it failed but more attempts allowed).
    3.  **Event:** `brute_force_tier1_triggered_on_unlock`
        *   **Condition(s):** `did_brute_force_tier1_trigger == True`.
        *   **Action(s) during transition:** Log f"Brute force Tier 1 lockout triggered by PIN type {pin_type}."
        *   **Next State:** `BRUTE_FORCE_TIER1_LOCKOUT_DETECTED`
    4.  **Event:** `brute_force_tier2_triggered_on_unlock`
        *   **Condition(s):** `did_brute_force_tier2_trigger == True`.
        *   **Action(s) during transition:** Log f"Brute force Tier 2 lockout triggered by PIN type {pin_type}."
        *   **Next State:** `BRUTE_FORCE_TIER2_LOCKOUT_DETECTED`
    5.  **Event:** `unlock_confirmation_timeout_or_unexpected_pattern`
        *   **Condition(s):** None of the above.
        *   **Action(s) during transition:** Log f"ERROR: Timeout or unexpected LED pattern after PIN submission for type {pin_type}."
        *   **Next State:** `AUTOMATION_ERROR_STATE` (or back to `DEVICE_IN_STANDBY_MODE` with caution).

---
**State: `USER_MODE_UNLOCKED`**
*   **Description:** Device unlocked with User PIN. Data should be accessible.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_solid(LEDs['STABLE_ENUM'] or LEDs['USER_MODE_UNLOCKED_LED'], minimum=3, timeout=10, clear_buffer=True)` (Using a specific LED if defined)
    *   `at.confirm_enum()` (Verify USB drive is mounted/accessible)
    *   Log "User mode unlocked. Drive enumerated."
*   **Exit Actions:** `at.unmount_drive_if_needed()` (Hypothetical, if automation mounts it).
*   **Internal Actions/Events Handled (while in this state):**
    *   **Event (Automation Trigger):** `user_change_own_pin` (Payload: `current_user_pin_keys`, `new_user_pin_keys`, `new_user_pin_confirm_keys`)
        *   **Action(s):**
            *   Log "Attempting to change User PIN by user."
            *   `at.sequence(config.USER_CHANGE_PIN_START_KEYS)` (If a specific sequence starts this)
            *   `at.sequence(payload['current_user_pin_keys'])`
            *   `is_prompt_ok = at.await_led_state(LEDs['USER_NEW_PIN_ENTRY_PROMPT'], timeout=5)`
            *   If `is_prompt_ok`:
                *   `at.sequence(payload['new_user_pin_keys'])`
                *   `is_confirm_prompt_ok = at.await_led_state(LEDs['USER_NEW_PIN_CONFIRM_PROMPT'], timeout=5)`
                *   If `is_confirm_prompt_ok`:
                    *   `at.sequence(payload['new_user_pin_confirm_keys'])`
                    *   `is_accepted = at.await_led_state(LEDs['ACCEPT_PATTERN'], timeout=5)`
                    *   If `is_accepted`: Log "User PIN changed successfully."
                    *   Else: Log "User PIN change failed (rejected or timeout after confirm)."
                *   Else: Log "User PIN change failed (no confirm prompt for new PIN)."
            *   Else: Log "User PIN change failed (no prompt for new PIN after current PIN)."
        *   **(Stays in `USER_MODE_UNLOCKED` or temporary sub-state, logs outcome).**
    *   **Event (Automation Trigger):** `user_enroll_self_destruct_pin` (Payload: `current_user_pin_keys_for_auth`, `new_sd_pin_keys`, `new_sd_pin_confirm_keys`)
        *   **Action(s):**
            *   Log "Attempting to enroll Self-Destruct PIN by user."
            *   `at.sequence(config.USER_ENROLL_SD_PIN_START_KEYS)`
            *   `at.sequence(payload['current_user_pin_keys_for_auth'])`
            *   (Similar multi-step PIN entry and confirmation as above, tailored for SD PIN enrollment by user)
            *   Log success or failure.
        *   **(Stays in `USER_MODE_UNLOCKED` or temporary sub-state, logs outcome).**
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `request_lock_from_user_mode`
        *   **Action(s) during transition:** Log "Requesting lock from User Mode."
        *   **Next State:** `LOCKING_DEVICE`
    2.  **Event (Automation Trigger):** `request_power_off_from_user_mode`
        *   **Action(s) during transition:** Log "Requesting power off from User Mode."
        *   **Next State:** `POWERING_OFF`
    3.  **Event (Device Initiated / Automation Detected):** `unattended_autolock_triggered`
        *   **Condition(s):** Automation detects Standby LEDs after a period of inactivity if monitoring for this.
        *   **Action(s) during transition:** Log "Unattended autolock detected/triggered."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`

---
**State: `ADMIN_MODE_UNLOCKED_DATA`**
*   **Description:** Device unlocked with Admin PIN for data access.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_solid(LEDs['STABLE_ENUM'] or LEDs['ADMIN_MODE_UNLOCKED_LED'], minimum=3, timeout=10, clear_buffer=True)`
    *   `at.confirm_enum()`
    *   Log "Admin mode unlocked for data access. Drive enumerated."
*   **Exit Actions:** `at.unmount_drive_if_needed()`
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `request_lock_from_admin_data_mode`
        *   **Action(s) during transition:** Log "Requesting lock from Admin Data Mode."
        *   **Next State:** `LOCKING_DEVICE`
    2.  **Event (Automation Trigger):** `request_power_off_from_admin_data_mode`
        *   **Action(s) during transition:** Log "Requesting power off from Admin Data Mode."
        *   **Next State:** `POWERING_OFF`

---
**State: `SELF_DESTRUCT_MODE_UNLOCKED_DATA`**
*   **Description:** Self-Destruct PIN was accepted, and device *might* briefly allow data access before or during wipe. (This depends heavily on device behavior).
*   **Entry Actions (by Automation):**
    *   Log "Self-Destruct PIN accepted. Checking for temporary data access."
    *   `is_sd_enum_pattern = at.await_and_confirm_led_pattern(LEDs['ENUM_SELF_DESTRUCT'], timeout=10, clear_buffer=False)`
    *   If `is_sd_enum_pattern`:
        *   Try `at.confirm_enum(timeout=5)` (If it enumerates, data *might* be accessible).
        *   Log "Device enumerated briefly after SD PIN. Data might be accessible before wipe."
    *   Else:
        *   `at.confirm_led_pattern(LEDs['SELF_DESTRUCT_WIPE_ACTIVE_PATTERN'], clear_buffer=False)` (Check if it went straight to wiping)
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Internal or Timeout):** `self_destruct_wipe_process_dominant`
        *   **Action(s) during transition:** LED pattern changes to clear wiping indication or timeout waiting for data access.
        *   Log "Proceeding to monitor Self-Destruct wipe sequence."
        *   **Next State:** `SELF_DESTRUCT_SEQUENCE_ACTIVE_WIPING`

---
**State: `AWAITING_ADMIN_CONFIG_MODE_ENTRY`**
*   **Description:** Automation has submitted Admin PIN for config mode, awaiting confirmation.
*   **Entry Actions (by Automation, using `event_data.kwargs['admin_pin_sequence']`):**
    *   `admin_pin = event_data.kwargs['admin_pin_sequence']`
    *   Log "Submitting Admin PIN to enter Configuration Mode."
    *   `at.sequence(admin_pin)`
    *   `is_admin_mode_ok = at.await_led_state(LEDs['ADMIN_MODE'], timeout=10, clear_buffer=False)` (e.g. Blue LED solid/blinking)
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `admin_config_mode_entry_successful`
        *   **Condition(s):** `is_admin_mode_ok == True`.
        *   **Action(s) during transition:** Log "Admin Configuration Mode entry successful."
        *   **Next State:** `ADMIN_MODE_CONFIGURING`
    2.  **Event:** `admin_config_mode_entry_failed`
        *   **Condition(s):** `is_admin_mode_ok == False`. (Check for `LEDs['REJECT_PATTERN']` internally if needed).
        *   **Action(s) during transition:** Log "ERROR: Admin Configuration Mode entry failed (PIN rejected or timeout)."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE` or `AUTOMATION_ERROR_STATE`.

---
**State: `ADMIN_MODE_CONFIGURING`**
*   **Description:** Device confirmed to be in Admin configuration mode. Automation can select actions.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_solid(LEDs['ADMIN_MODE'], minimum=2, timeout=5, clear_buffer=True)`
    *   Log "Device in Admin Configuration Mode. Awaiting action selection."
*   **Exit Actions:** None.
*   **Transitions Out (Examples for `#DEF_ADMIN_MODE_CONTENTS`):**
    1.  **Event (Automation Trigger):** `admin_select_enroll_user_pin`
        *   **Action(s) during transition:** `at.sequence(config.ADMIN_NAV_TO_ENROLL_USER_PIN_KEYS)`; Log "Navigating to Enroll User PIN."
        *   **Next State:** `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL` (Payload: `pin_type_to_enroll='user'`)
    2.  **Event (Automation Trigger):** `admin_select_change_admin_pin`
        *   **Action(s) during transition:** `at.sequence(config.ADMIN_NAV_TO_CHANGE_ADMIN_PIN_KEYS)`; Log "Navigating to Change Admin PIN."
        *   **Next State:** `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL` (Payload: `pin_type_to_enroll='admin_new'`, also needs current Admin PIN for auth usually before new one)
    3.  **Event (Automation Trigger):** `admin_select_enroll_self_destruct_pin`
        *   **Action(s) during transition:** `at.sequence(config.ADMIN_NAV_TO_ENROLL_SD_PIN_KEYS)`; Log "Navigating to Enroll Self-Destruct PIN."
        *   **Next State:** `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL` (Payload: `pin_type_to_enroll='self_destruct'`)
    4.  **Event (Automation Trigger):** `admin_select_enroll_recovery_pin` (Payload: `recovery_pin_index` if multiple)
        *   **Action(s) during transition:** `at.sequence(config.ADMIN_NAV_TO_ENROLL_RECOVERY_PIN_KEYS_FOR_INDEX[payload['recovery_pin_index']])`; Log "Navigating to Enroll Recovery PIN."
        *   **Next State:** `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL` (Payload: `pin_type_to_enroll='recovery'`)
    5.  **Event (Automation Trigger):** `admin_select_set_brute_force_counter`
        *   **Action(s) during transition:** `at.sequence(config.ADMIN_NAV_TO_SET_BF_COUNTER_KEYS)`; Log "Navigating to Set Brute Force Counter."
        *   **Next State:** `ADMIN_MODE_AWAITING_COUNTER_VALUE_INPUT` (Payload: `counter_type='brute_force'`)
    6.  **Event (Automation Trigger):** `admin_select_set_min_pin_length`
        *   **Action(s) during transition:** `at.sequence(config.ADMIN_NAV_TO_SET_MIN_PIN_KEYS)`; Log "Navigating to Set Min PIN Length."
        *   **Next State:** `ADMIN_MODE_AWAITING_COUNTER_VALUE_INPUT` (Payload: `counter_type='min_pin_length'`)
    7.  **Event (Automation Trigger):** `admin_select_toggle_feature` (Payload: `feature_name`, `keys_to_navigate_to_feature`, `keys_to_toggle_feature`)
        *   **Action(s) during transition:** `at.sequence(payload['keys_to_navigate_to_feature'])`; Log f"Navigating to toggle feature: {payload['feature_name']}."
        *   **Next State:** `ADMIN_MODE_TOGGLING_FEATURE` (Payload: `feature_name`, `keys_to_toggle_feature`)
    8.  **Event (Automation Trigger):** `admin_select_user_reset`
        *   **Condition(s):** `not at.is_provision_lock_enabled()`.
        *   **Action(s) during transition:** `at.sequence(config.ADMIN_NAV_TO_USER_RESET_KEYS)`; `at.sequence(config.CONFIRM_ACTION_KEY)`; Log "Navigating to and confirming User Reset."
        *   **Next State:** `ADMIN_MODE_INITIATING_USER_RESET`
    9.  **Event (Automation Trigger):** `exit_admin_mode`
        *   **Action(s) during transition:** `at.sequence(config.ADMIN_EXIT_KEYS)`; Log "Exiting Admin Mode."
        *   **Next State:** `LOCKING_DEVICE` (typically locks when exiting admin)
    10. **Event (Automation Trigger):** `request_power_off_from_admin_config`
        *   **Action(s) during transition:** Log "Requesting power off from Admin Configuration Mode."
        *   **Next State:** `POWERING_OFF`

---
**State: `ADMIN_MODE_NAVIGATING_MENU`**
*   **Description:** Intermediate state if admin menus are complex and require multiple key presses to reach an option. (Often too granular, can be part of action trigger's initial sequence).
*   **Entry Actions (by Automation, `event_data.kwargs['navigation_keys']`, `event_data.kwargs['expected_led_after_nav']`):**
    *   Log f"Navigating Admin Menu with keys: {event_data.kwargs['navigation_keys']}."
    *   `at.sequence(event_data.kwargs['navigation_keys'])`
    *   `nav_ok = at.await_led_state(event_data.kwargs['expected_led_after_nav'], timeout=5, clear_buffer=False)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `admin_menu_navigation_successful`
        *   **Condition(s):** `nav_ok == True`.
        *   **Action(s) during transition:** Log "Admin menu navigation step successful."
        *   **Next State:** (Target action state, e.g., `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL` or another `ADMIN_MODE_NAVIGATING_MENU` if multi-step nav)
    2.  **Event:** `admin_menu_navigation_failed`
        *   **Condition(s):** `nav_ok == False`.
        *   **Action(s) during transition:** Log "ERROR: Admin menu navigation step failed."
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Return to main admin menu, log error)

---
**State: `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL`**
*   **Description:** Admin action selected, device is prompting for a new PIN to be entered.
*   **Entry Actions (by Automation, Payload: `pin_type_to_enroll`):**
    *   `self.current_pin_enroll_type = event_data.kwargs['pin_type_to_enroll']`
    *   `is_prompt_ok = at.await_led_state(LEDs['ADMIN_NEW_PIN_ENTRY_PROMPT'], timeout=5, clear_buffer=False)`
    *   If `is_prompt_ok`:
        *   Log f"Ready to enter new PIN for enrollment type: {self.current_pin_enroll_type}."
    *   Else:
        *   Log f"ERROR: Did not see PIN entry prompt for {self.current_pin_enroll_type}."
        *   `self.to_ADMIN_MODE_CONFIGURING()` (Error, go back to admin menu)
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `submit_new_pin_for_enrollment` (Payload: `new_pin_keys`, `new_pin_confirm_keys` if applicable)
        *   **Condition(s):** `is_prompt_ok == True` (from entry actions).
        *   **Action(s) during transition:** Log "Submitting new PIN for enrollment."
        *   **Next State:** `ADMIN_MODE_ENTERING_NEW_PIN`

---
**State: `ADMIN_MODE_ENTERING_NEW_PIN`**
*   **Description:** Automation is inputting the first instance of the new PIN during Admin configuration.
*   **Entry Actions (by Automation, Payload: `new_pin_keys`, `new_pin_confirm_keys`):**
    *   `self.current_new_pin_confirm_keys = event_data.kwargs.get('new_pin_confirm_keys')`
    *   Log "Entering new PIN (first instance)."
    *   `at.sequence(event_data.kwargs['new_pin_keys'])`
    *   `is_confirm_prompt_ok = at.await_led_state(LEDs['ADMIN_NEW_PIN_CONFIRM_PROMPT'], timeout=5, clear_buffer=False)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `new_pin_entry_accepted_await_confirmation`
        *   **Condition(s):** `is_confirm_prompt_ok == True`.
        *   **Action(s) during transition:** Log "New PIN first entry accepted, awaiting confirmation input."
        *   **Next State:** `ADMIN_MODE_AWAITING_NEW_PIN_CONFIRMATION` (Payload: `new_pin_confirm_keys = self.current_new_pin_confirm_keys`)
    2.  **Event:** `new_pin_entry_rejected_or_timeout`
        *   **Condition(s):** `is_confirm_prompt_ok == False`.
        *   **Action(s) during transition:** Log "ERROR: New PIN first entry rejected or no confirmation prompt."
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (or retry `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL`)

---
**State: `ADMIN_MODE_AWAITING_NEW_PIN_CONFIRMATION`**
*   **Description:** Automation is inputting the PIN a second time for confirmation during Admin configuration.
*   **Entry Actions (by Automation, Payload: `new_pin_confirm_keys`):**
    *   Log "Entering new PIN (confirmation instance)."
    *   `at.sequence(event_data.kwargs['new_pin_confirm_keys'])`
    *   `is_accepted = at.await_led_state(LEDs['ACCEPT_PATTERN'], timeout=5, clear_buffer=False)`
    *   `is_rejected = False`
    *   If not `is_accepted`:
        *   `is_rejected = at.confirm_led_pattern(LEDs['REJECT_PATTERN'], clear_buffer=False)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `new_pin_enroll_action_successful`
        *   **Condition(s):** `is_accepted == True`.
        *   **Action(s) during transition:** Log "New PIN enrollment/change successful (Admin mode)."
        *   **Next State:** `ADMIN_MODE_CONFIGURING`
    2.  **Event:** `new_pin_enroll_action_failed_mismatch_or_rejected`
        *   **Condition(s):** `is_rejected == True` or (`is_accepted == False` and `is_rejected == False` -> timeout).
        *   **Action(s) during transition:** Log "ERROR: New PIN enrollment/change failed (mismatch, rejected, or timeout)."
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Log failure, user might need to retry action)

---
**State: `ADMIN_MODE_AWAITING_COUNTER_VALUE_INPUT`**
*   **Description:** Admin action selected, device is prompting for numeric counter input.
*   **Entry Actions (by Automation, Payload: `counter_type`):**
    *   `self.current_counter_type = event_data.kwargs['counter_type']`
    *   `is_prompt_ok = at.await_led_state(LEDs['ADMIN_COUNTER_ENTRY_PROMPT'], timeout=5, clear_buffer=False)`
    *   If `is_prompt_ok`:
        *   Log f"Ready to enter value for counter: {self.current_counter_type}."
    *   Else:
        *   Log f"ERROR: Did not see counter entry prompt for {self.current_counter_type}."
        *   `self.to_ADMIN_MODE_CONFIGURING()` (Error, go back to admin menu)
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `submit_counter_value` (Payload: `counter_value_keys`)
        *   **Condition(s):** `is_prompt_ok == True` (from entry actions).
        *   **Action(s) during transition:** Log "Submitting counter value."
        *   **Next State:** `ADMIN_MODE_ENTERING_COUNTER_VALUE`

---
**State: `ADMIN_MODE_ENTERING_COUNTER_VALUE`**
*   **Description:** Automation is inputting digits for the counter during Admin configuration.
*   **Entry Actions (by Automation, Payload: `counter_value_keys`):**
    *   Log "Entering counter value."
    *   `at.sequence(event_data.kwargs['counter_value_keys'])`
    *   `at.press(config.CONFIRM_ACTION_KEY)` (or specific key to finalize counter input)
    *   `is_accepted = at.await_led_state(LEDs['ACCEPT_PATTERN'], timeout=5, clear_buffer=False)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `counter_set_action_successful`
        *   **Condition(s):** `is_accepted == True`.
        *   **Action(s) during transition:** Log "Counter value set successfully (Admin mode)."
        *   **Next State:** `ADMIN_MODE_CONFIGURING`
    2.  **Event:** `counter_set_action_failed`
        *   **Condition(s):** `is_accepted == False`.
        *   **Action(s) during transition:** Log "ERROR: Counter value set action failed."
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Log failure)

---
**State: `ADMIN_MODE_TOGGLING_FEATURE`**
*   **Description:** Automation is sending sequence to toggle a feature and confirming outcome.
*   **Entry Actions (by Automation, Payload: `feature_name`, `keys_to_toggle_feature`):**
    *   `feature_to_toggle = event_data.kwargs['feature_name']`
    *   Log f"Attempting to toggle feature: {feature_to_toggle}."
    *   `at.sequence(event_data.kwargs['keys_to_toggle_feature'])`
    *   `is_accepted = at.await_led_state(LEDs['ACCEPT_PATTERN'] or LEDs['ADMIN_MODE'], timeout=5, clear_buffer=False)` (Feedback can vary; device might show accept then return to admin mode, or just stay in admin mode with new setting active)
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `feature_toggle_successful`
        *   **Condition(s):** `is_accepted == True`.
        *   **Action(s) during transition:** Log f"Feature '{feature_to_toggle}' toggle successful."
        *   **Next State:** `ADMIN_MODE_CONFIGURING`
    2.  **Event:** `feature_toggle_failed`
        *   **Condition(s):** `is_accepted == False`.
        *   **Action(s) during transition:** Log f"ERROR: Feature '{feature_to_toggle}' toggle failed or timed out."
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Log failure)

---
**State: `ADMIN_MODE_INITIATING_USER_RESET`**
*   **Description:** User Reset (Factory Default) command confirmed from Admin Mode. Awaiting reset process.
*   **Entry Actions (by Automation):**
    *   Log "User Reset from Admin Mode confirmed by automation. Awaiting device reset process."
    *   `is_reset_confirm_pattern_ok = at.confirm_led_pattern(LEDs['FACTORY_RESET_CONFIRMATION_FROM_ADMIN_PATTERN'] or LEDs['FACTORY_RESET_IN_PROGRESS_PATTERN'], clear_buffer=False)` (Device shows specific feedback then proceeds to reset)
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `user_reset_process_started_from_admin`
        *   **Condition(s):** `is_reset_confirm_pattern_ok == True`.
        *   **Action(s) during transition:** Log "Device is now proceeding with factory reset from Admin command."
        *   **Next State:** `FACTORY_RESET_IN_PROGRESS`
    2.  **Event:** `user_reset_start_failed_from_admin`
        *   **Condition(s):** `is_reset_confirm_pattern_ok == False`.
        *   **Action(s) during transition:** Log "ERROR: Failed to confirm start of factory reset process from Admin."
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Log error, return to admin menu)

---
**State: `AWAITING_UFE_START_CONFIRMATION`**
*   **Description:** UFE hardware sequence sent from Standby, awaiting UFE mode LED confirmation.
*   **Entry Actions (by Automation):**
    *   Log "Awaiting User Forced Enrollment mode confirmation."
    *   `is_ufe_mode_ok = at.await_led_state(LEDs['UFE_AWAIT_ADMIN_AUTH_PATTERN'], timeout=5, clear_buffer=False)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `ufe_start_successful_await_admin_auth`
        *   **Condition(s):** `is_ufe_mode_ok == True`.
        *   **Action(s) during transition:** Log "User Forced Enrollment mode confirmed. Awaiting Admin PIN."
        *   **Next State:** `UFE_AWAITING_ADMIN_PIN_AUTH`
    2.  **Event:** `ufe_start_failed_to_confirm`
        *   **Condition(s):** `is_ufe_mode_ok == False`.
        *   **Action(s) during transition:** Log "WARNING: Failed to confirm User Forced Enrollment mode. Returning to Standby."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`

---
**State: `UFE_AWAITING_ADMIN_PIN_AUTH`**
*   **Description:** UFE mode active, awaiting Admin PIN to authorize.
*   **Entry Actions (by Automation):** Log "UFE: Awaiting Admin PIN for authorization."
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `submit_admin_pin_for_ufe` (Payload: `admin_pin_sequence`)
        *   **Action(s) during transition:**
            *   Log "UFE: Submitting Admin PIN for authorization."
            *   `at.sequence(event_data.kwargs['admin_pin_sequence'])`
            *   `is_admin_auth_ok = at.await_led_state(LEDs['UFE_AWAIT_NEW_USER_PIN_PATTERN'], timeout=10, clear_buffer=False)` (Or `ACCEPT_PATTERN` then this)
            *   If `is_admin_auth_ok`:
                *   `self.ufe_admin_auth_successful()`
            *   Else: # Check for REJECT_PATTERN
                *   `is_rejected = at.confirm_led_pattern(LEDs['REJECT_PATTERN'], clear_buffer=False)`
                *   `self.ufe_admin_auth_failed(rejected=is_rejected)`
    2.  **Event (Internal):** `ufe_admin_auth_successful`
        *   **Action(s) during transition:** Log "UFE: Admin PIN authorization successful."
        *   **Next State:** `UFE_AWAITING_NEW_USER_PIN_ENROLL`
    3.  **Event (Internal):** `ufe_admin_auth_failed` (Payload: `rejected`)
        *   **Action(s) during transition:** Log f"UFE: Admin PIN authorization failed (Rejected: {event_data.kwargs.get('rejected', False)})."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`
    4.  **Event (Automation Trigger or Timeout):** `ufe_admin_auth_timeout_or_cancel`
        *   **Action(s) during transition:** Log "UFE: Admin PIN authorization timed out or cancelled."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`

---
**State: `UFE_AWAITING_NEW_USER_PIN_ENROLL`**
*   **Description:** UFE Admin Auth OK, device prompting for new User PIN.
*   **Entry Actions (by Automation):** Log "UFE: Awaiting new User PIN enrollment."
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `submit_new_user_pin_for_ufe` (Payload: `new_user_pin_keys`, `new_user_pin_confirm_keys`)
        *   **Action(s) during transition:**
            *   Log "UFE: Submitting new User PIN."
            *   `at.sequence(event_data.kwargs['new_user_pin_keys'])`
            *   `is_confirm_prompt_ok = at.await_led_state(LEDs['UFE_NEW_USER_PIN_CONFIRM_PROMPT'], timeout=5, clear_buffer=False)`
            *   `is_enroll_accepted = False`
            *   If `is_confirm_prompt_ok`:
                *   `at.sequence(event_data.kwargs['new_user_pin_confirm_keys'])`
                *   `is_enroll_accepted = at.await_led_state(LEDs['ACCEPT_PATTERN'], timeout=5, clear_buffer=False)`
            *   If `is_enroll_accepted`:
                *   `self.ufe_new_user_pin_enroll_successful()`
            *   Else:
                *   `self.ufe_new_user_pin_enroll_failed()`
    2.  **Event (Internal):** `ufe_new_user_pin_enroll_successful`
        *   **Action(s) during transition:** Log "UFE: New User PIN enrolled successfully. Device should return to Standby."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`
    3.  **Event (Internal):** `ufe_new_user_pin_enroll_failed`
        *   **Action(s) during transition:** Log "UFE: New User PIN enrollment failed."
        *   **Next State:** `UFE_AWAITING_NEW_USER_PIN_ENROLL` (For retry with limited attempts, or `DEVICE_IN_STANDBY_MODE` after max retries/cancel)

---
**State: `BRUTE_FORCE_TIER1_LOCKOUT_DETECTED`**
*   **Description:** Device showing Tier 1 Brute Force lockout LEDs. Automation must wait or power cycle.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER1_PATTERN'], clear_buffer=True)` (Clear buffer as this is a new distinct state)
    *   Log "Brute Force Tier 1 Lockout detected. Waiting for lockout period or power cycle."
    *   Start Tier 1 lockout timer (e.g., value from device spec, say 60 seconds).
*   **Exit Actions:** Stop Tier 1 lockout timer.
*   **Transitions Out:**
    1.  **Event (Timer Expires):** `tier1_lockout_period_expired`
        *   **Action(s) during transition:**
            *   Log "Tier 1 lockout period presumed expired."
            *   `is_standby = at.await_led_state(LEDs['STANDBY_MODE'], timeout=5, clear_buffer=True)` (Device should revert to Standby)
            *   If `is_standby`: `self.tier1_recovery_to_standby_successful()`
            *   Else: `self.tier1_recovery_to_standby_failed()`
    2.  **Event (Internal):** `tier1_recovery_to_standby_successful`
        *   **Action(s) during transition:** Log "Device returned to Standby Mode after Tier 1 lockout."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`
    3.  **Event (Internal):** `tier1_recovery_to_standby_failed`
        *   **Action(s) during transition:** Log "ERROR: Device did not return to Standby after Tier 1 lockout period."
        *   **Next State:** `AUTOMATION_ERROR_STATE`
    4.  **Event (Automation Trigger):** `force_power_cycle_during_tier1_lockout`
        *   **Action(s) during transition:** Log "Forcing power cycle during Tier 1 lockout."
        *   **Next State:** `POWERING_OFF` (Then `POWERING_ON` -> `VERIFYING_POST`. BF counter might persist or reset depending on device).
    5.  **Event (Device Feature - From `DEF_BRUTE_FORCE_1_TRIGGER_DETAILS`):** `initiate_last_try_login_tier1`
        *   **Action(s) during transition:** Log "Attempting last try login from Tier 1 lockout."
        *   **Next State:** `AWAITING_PIN_INPUT` (Payload: `pin_sequence`, `pin_type='last_try_tier1'`, `expected_unlock_success_pattern`, `target_successful_state`, context indicating this is a last try).
        *   *(If this last try fails in `AWAITING_UNLOCK_CONFIRMATION`):*
            *   If `!at.is_provision_lock_enabled()`: Transition to `INITIATING_FACTORY_RESET` (Payload: `source_state='BRUTE_FORCE_TIER1_LAST_FAIL_NO_PL'`)
            *   Else (if it escalates to Tier 2 or specific behavior): Transition to `BRUTE_FORCE_TIER2_LOCKOUT_DETECTED` or `AUTOMATION_ERROR_STATE`.

---
**State: `BRUTE_FORCE_TIER2_LOCKOUT_DETECTED`**
*   **Description:** Device showing Tier 2 Brute Force lockout LEDs. Outcome depends on Provision Lock.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER2_PATTERN'], clear_buffer=True)`
    *   Log "Brute Force Tier 2 Lockout detected."
    *   `is_pl_enabled = at.is_provision_lock_enabled()` (Hypothetical check)
    *   If `is_pl_enabled`: `self.tier2_lockout_provision_lock_enabled()`
    *   Else: `self.tier2_lockout_provision_lock_disabled_initiating_reset()`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Internal):** `tier2_lockout_provision_lock_enabled`
        *   **Action(s) during transition:** Log "Tier 2 Lockout with Provision Lock active. Proceeding to Bricked state."
        *   **Next State:** `DEVICE_BRICKED_AWAITING_ADMIN_RECOVERY_PIN`
    2.  **Event (Internal):** `tier2_lockout_provision_lock_disabled_initiating_reset`
        *   **Action(s) during transition:** Log "Tier 2 Lockout with Provision Lock disabled. Initiating factory reset."
        *   **Next State:** `INITIATING_FACTORY_RESET` (Payload: `source_state='BRUTE_FORCE_TIER2_NO_PL'`)

---
**State: `DEVICE_BRICKED_AWAITING_ADMIN_RECOVERY_PIN`**
*   **Description:** Device is bricked (BF Tier 2 + Provision Lock). Only Admin Recovery PIN might save it. Max 5 attempts for Admin Recovery PIN.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_solid(LEDs['DEVICE_BRICKED_AWAIT_RECOVERY_PATTERN'], timeout=10, clear_buffer=True)`
    *   Log "Device bricked due to Brute Force with Provision Lock. Awaiting Admin Recovery PIN."
    *   If not hasattr(self, 'admin_recovery_attempts') or new entry: `self.admin_recovery_attempts = 0`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `submit_admin_recovery_pin` (Payload: `recovery_pin_sequence`)
        *   **Condition(s):** `self.admin_recovery_attempts < 5`.
        *   **Action(s) during transition:**
            *   `self.admin_recovery_attempts += 1`
            *   Log f"Submitting Admin Recovery PIN (Attempt {self.admin_recovery_attempts}/5)."
            *   `at.sequence(event_data.kwargs['recovery_pin_sequence'])`
            *   `is_recovery_accepted = at.await_led_state(LEDs['FACTORY_RESET_START_AFTER_RECOVERY_PATTERN'] or LEDs['ACCEPT_PATTERN'], timeout=10, clear_buffer=False)`
            *   `is_recovery_rejected = False`
            *   If not `is_recovery_accepted`:
                *   `is_recovery_rejected = at.confirm_led_pattern(LEDs['REJECT_PATTERN'], clear_buffer=False)`

            *   If `is_recovery_accepted`: `self.admin_recovery_successful()`
            *   Else if `is_recovery_rejected` AND `self.admin_recovery_attempts < 5`: `self.admin_recovery_pin_rejected_retry()`
            *   Else: `self.admin_recovery_failed_permanently_bricked()` # Max attempts reached or unexpected
    2.  **Event (Internal):** `admin_recovery_successful`
        *   **Action(s) during transition:** Log "Admin Recovery PIN accepted. Device will factory reset."
        *   **Next State:** `INITIATING_FACTORY_RESET` (Payload: `source_state='ADMIN_RECOVERY_SUCCESS'`)
    3.  **Event (Internal):** `admin_recovery_pin_rejected_retry`
        *   **Action(s) during transition:** Log "Admin Recovery PIN rejected. More attempts remaining."
        *   **Next State:** `DEVICE_BRICKED_AWAITING_ADMIN_RECOVERY_PIN` (Stays in state for more attempts)
    4.  **Event (Internal):** `admin_recovery_failed_permanently_bricked`
        *   **Action(s) during transition:** Log "Admin Recovery PIN failed after maximum attempts or critical error. Device permanently bricked."
        *   **Next State:** `DEVICE_PERMANENTLY_BRICKED_DETECTED`
    5.  **Event (Automation Trigger):** `request_power_off_from_bricked_state`
        *   **Action(s) during transition:** Log "Requesting power off from Bricked state."
        *   **Next State:** `POWERING_OFF` (Device should remain bricked on next power on)

---
**State: `DEVICE_PERMANENTLY_BRICKED_DETECTED`**
*   **Description:** Device LEDs indicate it's unrecoverable.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_solid(LEDs['PERMANENTLY_BRICKED_PATTERN'], timeout=10, clear_buffer=True)`
    *   Log "DEVICE PERMANENTLY BRICKED. No further automated actions possible."
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `acknowledge_permanent_brick_and_power_off`
        *   **Action(s) during transition:** Log "Acknowledging permanent brick state and powering off."
        *   **Next State:** `POWERING_OFF`

---
**State: `INITIATING_FACTORY_RESET`**
*   **Description:** Factory Reset command issued (from Admin, Brute Force, Self-Destruct, OOB, Standby), awaiting process start.
*   **Entry Actions (by Automation, Payload: `source_state`):**
    *   Log f"Factory Reset initiated from source: {event_data.kwargs['source_state']}. Awaiting reset process to start."
    *   `is_reset_started = at.await_led_state(LEDs['FACTORY_RESET_IN_PROGRESS_PATTERN'], timeout=10, clear_buffer=False)` (Device should show feedback then start reset)
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `factory_reset_process_started`
        *   **Condition(s):** `is_reset_started == True`.
        *   **Action(s) during transition:** Log "Factory reset process has started (LEDs confirmed)."
        *   **Next State:** `FACTORY_RESET_IN_PROGRESS`
    2.  **Event:** `factory_reset_start_failed`
        *   **Condition(s):** `is_reset_started == False`.
        *   **Action(s) during transition:** Log "ERROR: Failed to confirm start of factory reset process."
        *   **Next State:** `AUTOMATION_ERROR_STATE` (or `DEVICE_PERMANENTLY_BRICKED_DETECTED` if reset is critical and fails to start)

---
**State: `FACTORY_RESET_IN_PROGRESS`**
*   **Description:** Observing Factory Reset LED pattern.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_pattern(LEDs['FACTORY_RESET_IN_PROGRESS_PATTERN'], clear_buffer=True)` (Ensure it's solidly in this pattern)
    *   Log "Factory Reset in progress. Awaiting completion and device reboot/OOB mode."
    *   Start long timer (e.g., value from device spec, 60-180 seconds).
*   **Exit Actions:** Stop timer.
*   **Transitions Out:**
    1.  **Event (Timer Expires or LED change):** `factory_reset_completed_oob_detected`
        *   **Condition(s):** `at.await_led_state(LEDs['OOB_MODE_PATTERN'] or LEDs['STANDBY_MODE'], timeout=LONG_RESET_TIMEOUT, clear_buffer=True)` indicating reset finished, device likely in OOB after a POST.
        *   **Action(s) during transition:** Log "Factory reset appears complete. Device should reboot or be in OOB mode."
        *   **Next State:** `VERIFYING_POST` (as device usually reboots and goes through POST after reset) or directly to `DEVICE_IN_OOB_MODE` if POST is implicitly confirmed by OOB pattern and no reboot observed.
    2.  **Event (Timer Expires with no OOB/Standby or Error LED):** `factory_reset_failed_or_timeout`
        *   **Action(s) during transition:** Log "ERROR: Factory reset timed out or ended in an unexpected state."
        *   **Next State:** `AUTOMATION_ERROR_STATE` or `DEVICE_PERMANENTLY_BRICKED_DETECTED`.

---
**State: `SELF_DESTRUCT_SEQUENCE_ACTIVE_WIPING`**
*   **Description:** Self-Destruct PIN was accepted. Device is actively wiping data or has completed wiping and is resetting.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_pattern(LEDs['SELF_DESTRUCT_WIPE_ACTIVE_PATTERN'], clear_buffer=False)` (e.g. rapid red blinking)
    *   Log "Self-destruct sequence active. Awaiting device reset to OOB or factory reset completion."
    *   Start long timer (e.g., value from device spec, 60-300 seconds).
*   **Exit Actions:** Stop timer.
*   **Transitions Out:**
    1.  **Event:** `self_destruct_wipe_completed_leading_to_reset`
        *   **Condition(s):** `at.await_led_state(LEDs['FACTORY_RESET_IN_PROGRESS_PATTERN'], timeout=LONG_WIPE_TIMEOUT, clear_buffer=True)` or directly to OOB/POST. (Self-destruct often triggers a full factory reset.)
        *   **Action(s) during transition:** Log "Self-destruct wipe appears complete, device proceeding to factory reset or OOB."
        *   **Next State:** `FACTORY_RESET_IN_PROGRESS` or `VERIFYING_POST` (if it reboots into POST).
    2.  **Event:** `self_destruct_wipe_failed_or_timeout`
        *   **Action(s) during transition:** Log "ERROR: Timeout waiting for reset after self-destruct, or error pattern detected."
        *   **Next State:** `AUTOMATION_ERROR_STATE` or `DEVICE_PERMANENTLY_BRICKED_DETECTED`

---
**State: `AWAITING_DIAGNOSTIC_MODE_ENTRY`**
*   **Description:** Diagnostic mode entry sequence sent, awaiting confirmation (e.g., version display).
*   **Entry Actions (by Automation):**
    *   Log "Awaiting Diagnostic Mode entry confirmation (version display pattern)."
    *   `is_diag_ok = at.await_led_state(LEDs['DIAGNOSTIC_MODE_VERSION_DISPLAY_PATTERN'] or LEDs['DIAGNOSTIC_MODE'], timeout=10, clear_buffer=False)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `diagnostic_mode_entry_successful`
        *   **Condition(s):** `is_diag_ok == True`.
        *   **Action(s) during transition:** Log "Diagnostic Mode entry successful."
        *   **Next State:** `DIAGNOSTIC_MODE_DISPLAYING_INFO`
    2.  **Event:** `diagnostic_mode_entry_failed`
        *   **Condition(s):** `is_diag_ok == False`.
        *   **Action(s) during transition:** Log "ERROR: Failed to enter Diagnostic Mode."
        *   **Next State:** (Source state, e.g., `DEVICE_IN_OOB_MODE` or `DEVICE_IN_STANDBY_MODE`, log error)

---
**State: `DIAGNOSTIC_MODE_DISPLAYING_INFO`**
*   **Description:** Device is displaying version/ID info. Automation might try to capture this or wait for keypad test.
*   **Entry Actions (by Automation):**
    *   Log "Diagnostic Mode: Observing version/ID display."
    *   Start timer for info display (e.g., 10-20 seconds).
    *   `is_keypad_prompt_ok = at.await_led_state(LEDs['DIAGNOSTIC_KEYPAD_TEST_PROMPT_PATTERN'], timeout=20, clear_buffer=False)` (Wait for pattern indicating keypad test is ready).
*   **Exit Actions:** Stop info display timer.
*   **Transitions Out:**
    1.  **Event:** `diagnostic_info_display_complete_await_keypad_test`
        *   **Condition(s):** `is_keypad_prompt_ok == True`.
        *   **Action(s) during transition:** Log "Diagnostic info display complete, keypad test prompt observed."
        *   **Next State:** `DIAGNOSTIC_MODE_KEYPAD_TEST_ACTIVE`
    2.  **Event (Automation Trigger or Device Action):** `exit_diagnostic_mode_requested_during_info`
        *   **Action(s) during transition:** `at.sequence(config.DIAGNOSTIC_EXIT_KEYS)`; Log "Exiting Diagnostic Mode during info display."
        *   **Next State:** (Source state, e.g. `DEVICE_IN_OOB_MODE` or `DEVICE_IN_STANDBY_MODE`, after confirming exit pattern)
    3.  **Event:** `diagnostic_mode_timeout_or_error_during_info`
        *   **Condition(s):** `is_keypad_prompt_ok == False` and timer expired.
        *   **Action(s) during transition:** Log "ERROR: Timeout or error during Diagnostic Mode info display."
        *   **Next State:** `AUTOMATION_ERROR_STATE`

---
**State: `DIAGNOSTIC_MODE_KEYPAD_TEST_ACTIVE`**
*   **Description:** Keypad test is active within Diagnostics. Automation can press keys and observe feedback.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_solid(LEDs['DIAGNOSTIC_KEYPAD_TEST_PROMPT_PATTERN'], minimum=1, timeout=3, clear_buffer=True)`
    *   Log "Diagnostic Mode: Keypad test active."
*   **Exit Actions:** None.
*   **Internal Actions/Events Handled (while in this state):**
    *   **Event (Automation Trigger):** `test_diagnostic_keypad_button` (Payload: `key_to_press`, `expected_led_feedback_for_key`)
        *   **Action(s):**
            *   Log f"Testing keypad button: {event_data.kwargs['key_to_press']}."
            *   `at.press(event_data.kwargs['key_to_press'])`
            *   `feedback_ok = at.confirm_led_pattern(event_data.kwargs['expected_led_feedback_for_key'], clear_buffer=False)`
            *   Log f"Keypad button {event_data.kwargs['key_to_press']} test: {'PASS' if feedback_ok else 'FAIL'}."
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `exit_diagnostic_mode_after_keypad_test`
        *   **Action(s) during transition:** `at.sequence(config.DIAGNOSTIC_EXIT_KEYS)`; Log "Exiting Diagnostic Mode after keypad test."
        *   **Next State:** (Source state, e.g. `DEVICE_IN_OOB_MODE` or `DEVICE_IN_STANDBY_MODE` after confirming exit pattern like Standby LED)
    2.  **Event (Device Timeout):** `diagnostic_keypad_test_timeout` (If device auto-exits after inactivity)
        *   **Action(s) during transition:** Log "Diagnostic keypad test timed out (device auto-exited)."
        *   **Next State:** (Source state)

---
**State: `DEVICE_IN_SLEEP_MODE`**
*   **Description:** For devices that support a distinct sleep mode controllable/detectable by automation.
*   **Entry Actions (by Automation):**
    *   `at.confirm_led_solid(LEDs['SLEEP_MODE'], minimum=2, timeout=5, clear_buffer=True)`
    *   Log "Device confirmed in Sleep Mode."
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation Trigger):** `wake_device_from_sleep`
        *   **Action(s) during transition:** `at.press(config.WAKE_KEY)` (or any key if it wakes); Log "Attempting to wake device from sleep."
        *   **Next State:** `AWAKENING_FROM_SLEEP`
    2.  **Event (Automation Trigger):** `request_power_off_from_sleep_mode`
        *   **Action(s) during transition:** Log "Requesting power off from Sleep Mode."
        *   **Next State:** `POWERING_OFF` (Device might need to wake slightly to process power-off command)

---
**State: `AWAKENING_FROM_SLEEP`**
*   **Description:** Wake-up stimulus sent/detected, awaiting device to return to an active state (usually Standby).
*   **Entry Actions (by Automation):**
    *   Log "Awaiting device to awaken and return to Standby Mode."
    *   `is_standby_after_wake = at.await_led_state(LEDs['STANDBY_MODE'], timeout=5, clear_buffer=False)`
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event:** `device_awake_standby_confirmed`
        *   **Condition(s):** `is_standby_after_wake == True`.
        *   **Action(s) during transition:** Log "Device awakened successfully, Standby Mode confirmed."
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`
    2.  **Event:** `device_awaken_failed`
        *   **Condition(s):** `is_standby_after_wake == False`.
        *   **Action(s) during transition:** Log "ERROR: Device failed to awaken or return to Standby Mode."
        *   **Next State:** `AUTOMATION_ERROR_STATE`

---
**State: `AUTOMATION_ERROR_STATE`**
*   **Description:** Automation has encountered an unrecoverable error or unexpected device behavior.
*   **Entry Actions (by Automation, `event_data.kwargs['reason']`):**
    *   `error_reason = event_data.kwargs.get('reason', 'Unknown error')`
    *   Log f"CRITICAL AUTOMATION ERROR: {error_reason}. Previous state: {event_data.transition.source if event_data and event_data.transition else 'N/A'}."
    *   `at.snapshot_current_leds_and_log()` (Hypothetical debug function).
    *   Consider attempting a graceful power off.
*   **Exit Actions:** None.
*   **Transitions Out:**
    1.  **Event (Automation/Manual Trigger):** `attempt_error_recovery_power_cycle`
        *   **Action(s) during transition:** Log "Attempting error recovery via power cycle."
        *   **Next State:** `POWERING_OFF` (then to `POWERING_ON` if successful)
    2.  **Event (Automation/Manual Trigger):** `halt_automation_due_to_error`
        *   **Action(s) during transition:** Log "Halting automation due to critical error."
        *   **(Stays in this state or transitions to a specific `HALTED` state).**

---

**IV. REUSABLE CONDITIONS / ACTIONS (for `at` controller and FSM logic):**

This section lists helper functions, conditions, and actions that the FSM's state transition logic will rely on. These are typically implemented as methods within the `UnifiedController` (`at`) or as direct FSM logic that uses `at`'s capabilities.

**A. PIN & Key Sequence Operations (Interacting with `at.sequence`, `at.press`):**
*   `at.sequence(key_list, press_duration_ms, pause_duration_ms)`: Sends a sequence of key presses.
    *   *Usage:* Entering PINs, navigating menus, triggering special functions.
*   `at.press(key_name, duration_ms)`: Presses a single key.
    *   *Usage:* Confirming actions, simple commands like "lock."
*   *FSM Responsibility:* The FSM needs to know *which* sequences or keys to send for each operation (e.g., `config.ADMIN_PIN_SEQUENCE`, `config.OOB_ADMIN_ENROLL_START_KEYS`). These would be predefined constants or configurations.

**B. LED State & Pattern Verification (Interacting with `at.confirm_led_solid`, `at.confirm_led_pattern`, etc.):**
*   `at.confirm_led_solid(target_led_state_dict, minimum_duration_s, timeout_s, clear_buffer_bool)` -> bool
    *   *Usage:* Verifying stable states like `STANDBY_MODE`, `ADMIN_MODE`, `ALL_OFF`.
*   `at.confirm_led_pattern(target_led_pattern_list, clear_buffer_bool)` -> bool
    *   *Usage:* Verifying dynamic sequences like `STARTUP` (POST), `ACCEPT_PATTERN`, `REJECT_PATTERN`, `BRUTE_FORCED_PATTERN`.
*   `at.await_led_state(target_led_state_dict, timeout_s, fail_leds_list, clear_buffer_bool)` -> bool
    *   *Usage:* Waiting for a specific LED state to appear, e.g., waiting for `ADMIN_NEW_PIN_ENTRY_PROMPT`.
*   `at.await_and_confirm_led_pattern(target_led_pattern_list, timeout_s, clear_buffer_bool)` -> bool
    *   *Usage:* Waiting for the *start* of a pattern and then confirming the whole pattern, e.g., `ENUM` pattern after PIN entry.
*   `at.snapshot_current_leds_and_log()` (Hypothetical debug function)
    *   *Usage:* In `AUTOMATION_ERROR_STATE` to log the exact LED state when an error occurred.
*   *FSM Responsibility:* The FSM needs to know which `LEDs[...]` definition corresponds to each expected device feedback.

**C. USB Device Enumeration & Access:**
*   `at.confirm_enum(stable_min_s, timeout_s)` -> bool (or raises error)
    *   *Usage:* Verifying the device's data partition is accessible via USB after unlock (User, Admin Data).
*   `at.unmount_drive_if_needed()` (Hypothetical)
    *   *Usage:* Cleanly unmounting a drive before locking or powering off if the automation explicitly mounted it. (Often OS-level, but `at` might wrap it).

**D. Device Configuration & Status Checks (May involve Admin Mode interaction or persistent state):**
*   `at.is_provision_lock_enabled()` -> bool
    *   *Usage:* Determining behavior for Brute Force Tier 2, User Reset.
    *   *Implementation Detail:* This might involve navigating Admin Mode to read the setting if not cached by the automation, or reading a status bit if the device exposes it directly.
*   `at.is_feature_enabled(feature_name)` -> bool (e.g., "SELF_DESTRUCT_PIN", "UNATTENDED_AUTO_LOCK")
    *   *Usage:* Conditional logic in FSM or test scripts.
    *   *Implementation Detail:* Similar to `is_provision_lock_enabled()`.
*   `at.get_device_firmware_version()` -> str (Hypothetical)
    *   *Usage:* Logging, compatibility checks. Might involve Diagnostic Mode or Admin Mode.
*   `at.get_brute_force_attempt_counter_value()` -> int (Hypothetical, if readable from device)
    *   *Usage:* More precise Brute Force handling.
*   `at.get_min_pin_length_setting_value()` -> int (Hypothetical, if readable from device)

**E. Power Control (Interacting with `at.on`, `at.off`):**
*   `at.on(phidget_channel_name)` (e.g., `at.on("usb3")`, `at.on("connect")`)
*   `at.off(phidget_channel_name)`
*   *FSM Responsibility:* Knowing which channels control power aspects.

**F. FSM Internal State Management & Timers:**
*   `self.current_pin_type`: Variable within FSM to track context (e.g. if PIN entry is for User, Admin, SD).
*   `self.admin_recovery_attempts`: Counter for Admin Recovery PIN tries.
*   `self.fsm_timer_start(timer_name, duration_s, timeout_event_name)`
*   `self.fsm_timer_cancel(timer_name)`
    *   *Usage:* For state-specific timeouts (e.g., Brute Force lockout period, waiting for Self-Destruct wipe). The `transitions` library has some built-in timeout capabilities for states, or this could be a simple helper.

**G. Logging:**
*   `self.logger.info/warning/error/critical/debug(...)`: Used throughout FSM actions and transitions.
*   `_log_state_change_details(event_data)`: Centralized logging for all state transitions.

**H. Hypothetical Higher-Level `at` Abstractions (Could be built upon primitives):**
*   `at.determine_initial_mode_after_post()` -> str ('OOB', 'STANDBY', 'UFE', 'BRUTE_FORCE', 'ERROR')
    *   *Usage:* Simplifies `VERIFYING_POST` transitions.
    *   *Implementation Detail:* Would internally use `await_led_state` or `confirm_one_of_patterns` for various known post-POST LED states.
*   `at.navigate_admin_menu_to(target_option_enum_or_name)` -> bool
    *   *Usage:* Simplifies reaching a specific Admin Mode option.
    *   *Implementation Detail:* Would use pre-defined key sequences for menu navigation.
*   `at.perform_admin_pin_enroll(pin_type_to_enroll, new_pin_keys, new_pin_confirm_keys)` -> bool
    *   *Usage:* Encapsulates the multi-step PIN enrollment process within Admin Mode.
*   `at.perform_admin_set_counter(counter_type, counter_value_keys)` -> bool
    *   *Usage:* Encapsulates setting a counter value in Admin Mode.

**I. Error Reason Propagation:**
*   When an `at` method fails or an unexpected condition occurs, the FSM event that transitions to an error state (e.g., `post_sequence_failed`, `critical_error_occurred`) should be triggered with a `reason` keyword argument.
    *   Example: `self.post_sequence_failed(reason="STARTUP_PATTERN_MISMATCH")`
    *   This `reason` is then available in `event_data.kwargs['reason']` within the `on_enter_ERROR_STATE` or `after='_handle_error_details'` callbacks for better logging and debugging.

---