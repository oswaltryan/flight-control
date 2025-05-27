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
**(Core States: `DEVICE_OFF`, `POWERING_ON`, `VERIFYING_POST`, `DEVICE_IN_STANDBY_MODE`, `LOCKING_DEVICE`, `POWERING_OFF`, `AUTOMATION_ERROR_STATE` - as previously defined, with `VERIFYING_POST` now branching based on detected mode)**

---
**State: `VERIFYING_POST` (Revised Transitions Out)**
*   ... (Entry Actions as before) ...
*   **Transitions Out:**
    1.  **Event:** `post_sequence_successful_oob_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_solid(LEDs['OOB_MODE_PATTERN'] or LEDs['STANDBY_MODE'], ...)` indicates OOB.
        *   **Next State:** `DEVICE_IN_OOB_MODE`
    2.  **Event:** `post_sequence_successful_standby_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_solid(LEDs['STANDBY_MODE'], ...)` indicates Standby.
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`
    3.  **Event:** `post_sequence_successful_ufe_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_solid(LEDs['UFE_AWAIT_ADMIN_AUTH_PATTERN'], ...)` indicates UFE mode.
        *   **Next State:** `UFE_AWAITING_ADMIN_PIN_AUTH`
    4.  **Event:** `post_sequence_successful_brute_force_tier1_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER1_PATTERN'], ...)`
        *   **Next State:** `BRUTE_FORCE_TIER1_LOCKOUT_DETECTED`
    5.  **Event:** `post_sequence_successful_brute_force_tier2_detected`
        *   **Condition(s):** `is_post_ok == True` AND `at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER2_PATTERN'], ...)`
        *   **Next State:** `BRUTE_FORCE_TIER2_LOCKOUT_DETECTED`
    6.  **Event:** `post_sequence_failed_or_unknown_state`
        *   **Condition(s):** `is_post_ok == False` OR no known state pattern detected after POST.
        *   **Next State:** `AUTOMATION_ERROR_STATE`

---
**State: `DEVICE_IN_OOB_MODE`**
*   ... (Entry Actions as before) ...
*   **Transitions Out:**
    1.  **Event (Automation):** `initiate_oob_admin_pin_enrollment`
        *   **Next State:** `AWAITING_OOB_ADMIN_PIN_ENROLL_START`
    2.  **Event (Automation):** `request_diagnostic_mode_from_oob`
        *   **Action(s):** `at.sequence(config.OOB_DIAGNOSTIC_MODE_KEYS)`
        *   **Next State:** `AWAITING_DIAGNOSTIC_MODE_ENTRY`
    3.  **Event (Automation):** `request_user_reset_from_oob`
        *   **Condition(s):** `not at.is_provision_lock_enabled()` (Hypothetical check, OOB usually allows reset).
        *   **Next State:** `INITIATING_FACTORY_RESET` (Payload: `source_state='OOB_MODE'`)
    4.  **Event (Automation):** `request_power_off_from_oob`
        *   **Next State:** `POWERING_OFF`

---
**State: `AWAITING_OOB_ADMIN_PIN_ENROLL_START`** & **`OOB_ADMIN_PIN_ENROLLING`**
*   (As previously defined)
*   **`OOB_ADMIN_PIN_ENROLLING` Transitions Out:**
    1.  **Event:** `oob_admin_pin_enroll_successful`
        *   ...
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Device often goes to Admin Mode after initial Admin PIN set) or `DEVICE_IN_STANDBY_MODE`.
    2.  ... (failure case) ...

---
**State: `DEVICE_IN_STANDBY_MODE` (Revised Transitions Out)**
*   ... (Entry Actions as before) ...
*   **Transitions Out:**
    1.  **Event (Automation):** `initiate_pin_unlock` (Payload: `pin_sequence`, `pin_type` \['user', 'admin_data', 'self_destruct', 'recovery'\], `expected_unlock_success_pattern`, `target_successful_state`)
        *   **Next State:** `AWAITING_PIN_INPUT`
    2.  **Event (Automation):** `initiate_admin_config_mode_entry` (Payload: `admin_pin_sequence`)
        *   **Next State:** `AWAITING_ADMIN_CONFIG_MODE_ENTRY`
    3.  **Event (Automation):** `initiate_user_forced_enrollment_start`
        *   **Action(s):** `at.sequence(config.UFE_START_KEYS_FROM_STANDBY)`
        *   **Next State:** `AWAITING_UFE_START_CONFIRMATION`
    4.  **Event (Automation):** `request_diagnostic_mode_from_standby`
        *   **Action(s):** `at.sequence(config.STANDBY_DIAGNOSTIC_MODE_KEYS)`
        *   **Next State:** `AWAITING_DIAGNOSTIC_MODE_ENTRY`
    5.  **Event (Automation):** `request_user_reset_from_standby`
        *   **Condition(s):** `not at.is_provision_lock_enabled()`.
        *   **Action(s):** `at.sequence(config.STANDBY_USER_RESET_KEYS)` (if direct key sequence exists, otherwise needs Admin)
        *   **Next State:** `INITIATING_FACTORY_RESET` (Payload: `source_state='STANDBY_MODE'`)
    6.  **Event (Automation):** `request_power_off_from_standby`
        *   **Next State:** `POWERING_OFF`
    7.  **Event (Automation, if applicable):** `request_sleep_mode`
        *   **Action(s):** `at.sequence(config.SLEEP_MODE_KEYS)` (if applicable)
        *   **Next State:** `DEVICE_IN_SLEEP_MODE` (after confirmation)

---
**State: `AWAITING_PIN_INPUT`**
*   **Description:** Generic state for automation inputting any PIN.
*   **Entry Actions (Payload: `pin_sequence`, `pin_type`, `expected_unlock_success_pattern`, `target_successful_state`):**
    *   `self.current_pin_type = event_data.kwargs['pin_type']`
    *   `at.sequence(event_data.kwargs['pin_sequence'])`
    *   `self.proceed_to_unlock_confirmation(expected_pattern=event_data.kwargs['expected_unlock_success_pattern'], target_state=event_data.kwargs['target_successful_state'], attempted_pin_type=self.current_pin_type)`
*   **Transitions Out:** (Handled by `proceed_to_unlock_confirmation` trigger)
    1.  **Event (Internal):** `proceed_to_unlock_confirmation` -> `AWAITING_UNLOCK_CONFIRMATION`

---
**State: `AWAITING_UNLOCK_CONFIRMATION` (Revised Transitions Out)**
*   ... (Entry Actions as before, checking for success, reject, brute_force patterns) ...
*   **Transitions Out:**
    1.  **Event:** `unlock_successful`
        *   **Next State:** `event_data.kwargs['target_state']` (e.g. `USER_MODE_UNLOCKED`, `ADMIN_MODE_UNLOCKED_DATA`, `SELF_DESTRUCT_SEQUENCE_ACTIVE_WIPING` if `pin_type` was 'self_destruct', `ADMIN_MODE_CONFIGURING` if `pin_type` was 'admin_recovery_from_bricked' and leads to reset then admin config, or `INITIATING_FACTORY_RESET` if recovery implies immediate reset).
    2.  **Event:** `unlock_pin_rejected`
        *   **Next State:** `DEVICE_IN_STANDBY_MODE` (or `DEVICE_BRICKED_AWAITING_ADMIN_RECOVERY_PIN` if `pin_type` was 'admin_recovery_from_bricked' and it failed but more attempts allowed).
    3.  **Event:** `brute_force_tier1_triggered_on_unlock`
        *   **Next State:** `BRUTE_FORCE_TIER1_LOCKOUT_DETECTED`
    4.  **Event:** `brute_force_tier2_triggered_on_unlock`
        *   **Next State:** `BRUTE_FORCE_TIER2_LOCKOUT_DETECTED`
    5.  **Event:** `unlock_confirmation_timeout_or_unexpected`
        *   **Next State:** `AUTOMATION_ERROR_STATE`

---
**State: `USER_MODE_UNLOCKED`**
*   ... (Entry Actions as before) ...
*   **Internal Actions/Events Handled (while in this state):**
    *   **Event (Automation):** `user_change_own_pin` (Payload: `old_pin_keys`, `new_pin_keys`, `new_pin_confirm_keys`)
        *   **Action(s):** `at.sequence(config.USER_CHANGE_PIN_START_KEYS)` -> `at.sequence(old_pin_keys)` -> ...
        *   Observe `LEDs['ACCEPT_PATTERN']` or `LEDs['REJECT_PATTERN']`. (Stays in `USER_MODE_UNLOCKED` or temporary sub-state).
    *   **Event (Automation):** `user_enroll_self_destruct_pin` (Payload: `user_pin_keys_for_auth`, `new_sd_pin_keys`, `new_sd_pin_confirm_keys`)
        *   **Action(s):** `at.sequence(config.USER_ENROLL_SD_PIN_START_KEYS)` -> `at.sequence(user_pin_keys_for_auth)` -> ...
        *   Observe feedback. (Stays in `USER_MODE_UNLOCKED` or temporary sub-state).
*   **Transitions Out:** (As before: Lock, Power Off, Autolock)

---
**State: `ADMIN_MODE_UNLOCKED_DATA`**
*   (Similar to `USER_MODE_UNLOCKED`, but fewer internal actions typically. Transitions: Lock, Power Off)

---
**State: `SELF_DESTRUCT_MODE_UNLOCKED_DATA`**
*   **Description:** Self-Destruct PIN was accepted, and device *might* briefly allow data access before or during wipe. (This depends heavily on device behavior).
*   **Entry Actions:**
    *   Log "Self-Destruct PIN accepted. Checking for temporary data access."
    *   `at.confirm_led_pattern(LEDs['ENUM_SELF_DESTRUCT'] or LEDs['SELF_DESTRUCT_WIPE_ACTIVE_PATTERN'])`
    *   Try `at.confirm_enum(timeout=5)` (If it enumerates, data *might* be accessible).
*   **Transitions Out:**
    1.  **Event:** `self_destruct_wipe_process_dominant`
        *   **Action(s):** LED pattern changes to clear wiping indication.
        *   **Next State:** `SELF_DESTRUCT_SEQUENCE_ACTIVE_WIPING`

---
**State: `AWAITING_ADMIN_CONFIG_MODE_ENTRY`** & **`ADMIN_MODE_CONFIGURING`**
*   (As previously defined)

---
**State: `ADMIN_MODE_CONFIGURING` (Revised Transitions Out for Admin Actions)**
*   ... (Entry Actions as before) ...
*   **Transitions Out (Examples for `#DEF_ADMIN_MODE_CONTENTS`):**
    1.  **Event (Automation):** `admin_select_enroll_user_pin`
        *   **Action(s):** `at.sequence(config.ADMIN_NAV_TO_ENROLL_USER_PIN_KEYS)`
        *   **Next State:** `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL` (Payload: `pin_type_to_enroll='user'`)
    2.  **Event (Automation):** `admin_select_change_admin_pin`
        *   **Action(s):** `at.sequence(config.ADMIN_NAV_TO_CHANGE_ADMIN_PIN_KEYS)`
        *   **Next State:** `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL` (Payload: `pin_type_to_enroll='admin_new'`)
    3.  **Event (Automation):** `admin_select_enroll_self_destruct_pin`
        *   **Action(s):** `at.sequence(config.ADMIN_NAV_TO_ENROLL_SD_PIN_KEYS)`
        *   **Next State:** `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL` (Payload: `pin_type_to_enroll='self_destruct'`)
    4.  **Event (Automation):** `admin_select_enroll_recovery_pin` (Assuming 4 recovery PINs might mean selecting which one or a general enroll)
        *   **Action(s):** `at.sequence(config.ADMIN_NAV_TO_ENROLL_RECOVERY_PIN_KEYS)`
        *   **Next State:** `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL` (Payload: `pin_type_to_enroll='recovery'`)
    5.  **Event (Automation):** `admin_select_set_brute_force_counter`
        *   **Action(s):** `at.sequence(config.ADMIN_NAV_TO_SET_BF_COUNTER_KEYS)`
        *   **Next State:** `ADMIN_MODE_AWAITING_COUNTER_VALUE_INPUT` (Payload: `counter_type='brute_force'`)
    6.  **Event (Automation):** `admin_select_set_min_pin_length`
        *   **Action(s):** `at.sequence(config.ADMIN_NAV_TO_SET_MIN_PIN_KEYS)`
        *   **Next State:** `ADMIN_MODE_AWAITING_COUNTER_VALUE_INPUT` (Payload: `counter_type='min_pin_length'`)
    7.  **Event (Automation):** `admin_select_toggle_feature` (Payload: `feature_name`, `keys_to_navigate_to_feature`, `keys_to_toggle_feature`)
        *   **Action(s):** `at.sequence(payload['keys_to_navigate_to_feature'])`
        *   **Next State:** `ADMIN_MODE_TOGGLING_FEATURE` (Payload: `feature_name`, `keys_to_toggle_feature`)
    8.  **Event (Automation):** `admin_select_user_reset`
        *   **Condition(s):** `not at.is_provision_lock_enabled()`.
        *   **Action(s):** `at.sequence(config.ADMIN_NAV_TO_USER_RESET_KEYS)` -> `at.sequence(config.CONFIRM_ACTION_KEY)`
        *   **Next State:** `ADMIN_MODE_INITIATING_USER_RESET`
    9.  **Event (Automation):** `exit_admin_mode`
        *   **Action(s):** `at.sequence(config.ADMIN_EXIT_KEYS)`
        *   **Next State:** `LOCKING_DEVICE` (typically locks when exiting admin)
    10. **Event (Automation):** `request_power_off_from_admin_config`
        *   **Next State:** `POWERING_OFF`

---
**State: `ADMIN_MODE_NAVIGATING_MENU`**
*   **Description:** Intermediate state if admin menus are complex and require multiple key presses to reach an option. (Often too granular, can be part of action trigger).
*   **Entry Actions:** `at.sequence(event_data.kwargs['navigation_keys'])` -> `confirm_led_or_timeout()`
*   **Transitions Out:** To next navigation step or target action state.

---
**State: `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL`**
*   **Description:** Admin action selected, device is prompting for a new PIN to be entered.
*   **Entry Actions (Payload: `pin_type_to_enroll`):**
    *   `self.current_pin_enroll_type = event_data.kwargs['pin_type_to_enroll']`
    *   `at.await_led_state(LEDs['ADMIN_NEW_PIN_ENTRY_PROMPT'], timeout=5)`
    *   Log "Ready to enter new PIN for {self.current_pin_enroll_type}."
*   **Transitions Out:**
    1.  **Event (Automation):** `submit_new_pin_for_enrollment` (Payload: `new_pin_keys`, `new_pin_confirm_keys`)
        *   **Next State:** `ADMIN_MODE_ENTERING_NEW_PIN`

---
**State: `ADMIN_MODE_ENTERING_NEW_PIN`**
*   **Description:** Automation is inputting the first instance of the new PIN.
*   **Entry Actions (Payload: `new_pin_keys`, `new_pin_confirm_keys`):**
    *   `at.sequence(event_data.kwargs['new_pin_keys'])`
    *   `at.await_led_state(LEDs['ADMIN_NEW_PIN_CONFIRM_PROMPT'], timeout=5)`
*   **Transitions Out:**
    1.  **Event:** `new_pin_entry_accepted_await_confirmation`
        *   **Next State:** `ADMIN_MODE_AWAITING_NEW_PIN_CONFIRMATION` (Payload: `new_pin_confirm_keys` from previous state)
    2.  **Event:** `new_pin_entry_rejected_or_timeout` (e.g. too short, invalid char)
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (or retry `ADMIN_MODE_AWAITING_PIN_FOR_CHANGE_OR_ENROLL`)

---
**State: `ADMIN_MODE_AWAITING_NEW_PIN_CONFIRMATION`**
*   **Description:** Automation is inputting the PIN a second time for confirmation.
*   **Entry Actions (Payload: `new_pin_confirm_keys`):**
    *   `at.sequence(event_data.kwargs['new_pin_confirm_keys'])`
    *   `is_accepted = at.await_led_state(LEDs['ACCEPT_PATTERN'], timeout=5)`
    *   `is_rejected = False`
    *   If not `is_accepted`: `is_rejected = at.confirm_led_pattern(LEDs['REJECT_PATTERN'], clear_buffer=False)`
*   **Transitions Out:**
    1.  **Event:** `new_pin_enroll_action_successful`
        *   **Condition(s):** `is_accepted == True`.
        *   **Next State:** `ADMIN_MODE_CONFIGURING`
    2.  **Event:** `new_pin_enroll_action_failed_mismatch_or_rejected`
        *   **Condition(s):** `is_rejected == True` or timeout.
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Log failure, user might need to retry action)

---
**State: `ADMIN_MODE_AWAITING_COUNTER_VALUE_INPUT`**
*   **Description:** Admin action selected, device is prompting for numeric counter input.
*   **Entry Actions (Payload: `counter_type`):**
    *   `self.current_counter_type = event_data.kwargs['counter_type']`
    *   `at.await_led_state(LEDs['ADMIN_COUNTER_ENTRY_PROMPT'], timeout=5)`
    *   Log "Ready to enter value for counter: {self.current_counter_type}."
*   **Transitions Out:**
    1.  **Event (Automation):** `submit_counter_value` (Payload: `counter_value_keys`)
        *   **Next State:** `ADMIN_MODE_ENTERING_COUNTER_VALUE`

---
**State: `ADMIN_MODE_ENTERING_COUNTER_VALUE`**
*   **Description:** Automation is inputting digits for the counter.
*   **Entry Actions (Payload: `counter_value_keys`):**
    *   `at.sequence(event_data.kwargs['counter_value_keys'])`
    *   `at.press(config.CONFIRM_ACTION_KEY)` (or specific key to finalize counter input)
    *   `is_accepted = at.await_led_state(LEDs['ACCEPT_PATTERN'], timeout=5)`
*   **Transitions Out:**
    1.  **Event:** `counter_set_action_successful`
        *   **Condition(s):** `is_accepted == True`.
        *   **Next State:** `ADMIN_MODE_CONFIGURING`
    2.  **Event:** `counter_set_action_failed`
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Log failure)

---
**State: `ADMIN_MODE_TOGGLING_FEATURE`**
*   **Description:** Automation is sending sequence to toggle a feature and confirming.
*   **Entry Actions (Payload: `feature_name`, `keys_to_toggle_feature`):**
    *   `at.sequence(event_data.kwargs['keys_to_toggle_feature'])`
    *   `is_accepted = at.await_led_state(LEDs['ACCEPT_PATTERN'] or LEDs['ADMIN_MODE'], timeout=5)` (Feedback can vary)
*   **Transitions Out:**
    1.  **Event:** `feature_toggle_successful`
        *   **Condition(s):** `is_accepted == True`.
        *   **Next State:** `ADMIN_MODE_CONFIGURING`
    2.  **Event:** `feature_toggle_failed`
        *   **Next State:** `ADMIN_MODE_CONFIGURING` (Log failure)

---
**State: `ADMIN_MODE_INITIATING_USER_RESET`**
*   **Description:** User Reset (Factory Default) command confirmed from Admin Mode.
*   **Entry Actions:**
    *   Log "User Reset from Admin Mode confirmed by automation."
    *   Device should show specific feedback then proceed to reset.
*   **Transitions Out:**
    1.  **Event:** `user_reset_process_started_from_admin`
        *   **Action(s):** `at.confirm_led_pattern(LEDs['FACTORY_RESET_CONFIRMATION_FROM_ADMIN_PATTERN'])`
        *   **Next State:** `FACTORY_RESET_IN_PROGRESS`

---
**State: `AWAITING_UFE_START_CONFIRMATION`**
*   **Description:** UFE hardware sequence sent from Standby, awaiting UFE mode LED confirmation.
*   **Entry Actions:**
    *   `is_ufe_mode_ok = at.await_led_state(LEDs['UFE_AWAIT_ADMIN_AUTH_PATTERN'], timeout=5)`
*   **Transitions Out:**
    1.  **Event:** `ufe_start_successful_await_admin_auth`
        *   **Condition(s):** `is_ufe_mode_ok == True`.
        *   **Next State:** `UFE_AWAITING_ADMIN_PIN_AUTH`
    2.  **Event:** `ufe_start_failed_to_confirm`
        *   **Next State:** `DEVICE_IN_STANDBY_MODE` (Log warning)

---
**State: `UFE_AWAITING_ADMIN_PIN_AUTH`**
*   **Description:** UFE mode active, awaiting Admin PIN to authorize.
*   **Entry Actions:** Log "UFE: Awaiting Admin PIN."
*   **Transitions Out:**
    1.  **Event (Automation):** `submit_admin_pin_for_ufe` (Payload: `admin_pin_sequence`)
        *   `at.sequence(payload['admin_pin_sequence'])`
        *   `is_admin_auth_ok = at.await_led_state(LEDs['UFE_AWAIT_NEW_USER_PIN_PATTERN'], timeout=10)` (Or `ACCEPT_PATTERN` then this)
        *   If `is_admin_auth_ok`: `self.ufe_admin_auth_successful()`
        *   Else (check for `REJECT_PATTERN`): `self.ufe_admin_auth_failed()`
    2.  **Event (Internal):** `ufe_admin_auth_successful`
        *   **Next State:** `UFE_AWAITING_NEW_USER_PIN_ENROLL`
    3.  **Event (Internal):** `ufe_admin_auth_failed`
        *   **Next State:** `DEVICE_IN_STANDBY_MODE` (Log failure)
    4.  **Event (Timeout/Cancel):** `ufe_admin_auth_timeout_or_cancel`
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`

---
**State: `UFE_AWAITING_NEW_USER_PIN_ENROLL`**
*   **Description:** UFE Admin Auth OK, device prompting for new User PIN.
*   **Entry Actions:** Log "UFE: Awaiting new User PIN."
*   **Transitions Out:**
    1.  **Event (Automation):** `submit_new_user_pin_for_ufe` (Payload: `new_user_pin_keys`, `new_user_pin_confirm_keys`)
        *   (Similar logic to `ADMIN_MODE_ENTERING_NEW_PIN` & `ADMIN_MODE_AWAITING_NEW_PIN_CONFIRMATION` but for UFE context)
        *   If success: `self.ufe_new_user_pin_enroll_successful()`
        *   Else: `self.ufe_new_user_pin_enroll_failed()`
    2.  **Event (Internal):** `ufe_new_user_pin_enroll_successful`
        *   **Action(s):** Device should return to Standby.
        *   **Next State:** `DEVICE_IN_STANDBY_MODE`
    3.  **Event (Internal):** `ufe_new_user_pin_enroll_failed`
        *   **Next State:** `UFE_AWAITING_NEW_USER_PIN_ENROLL` (For retry, or `DEVICE_IN_STANDBY_MODE` after max retries)

---
**State: `BRUTE_FORCE_TIER1_LOCKOUT_DETECTED`**
*   **Description:** Device showing Tier 1 Brute Force lockout LEDs. Automation must wait or power cycle.
*   **Entry Actions:**
    *   `at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER1_PATTERN'])`
    *   Log "Brute Force Tier 1 Lockout detected. Waiting for lockout period or power cycle."
    *   Start Tier 1 lockout timer (e.g., 1-2 minutes).
*   **Transitions Out:**
    1.  **Event (Timer Expires):** `tier1_lockout_period_expired`
        *   **Action(s):** `at.await_led_state(LEDs['STANDBY_MODE'], timeout=5)` (Device should revert to Standby)
        *   **Next State:** `DEVICE_IN_STANDBY_MODE` (or `AUTOMATION_ERROR_STATE` if not)
    2.  **Event (Automation):** `force_power_cycle_during_tier1_lockout`
        *   **Next State:** `POWERING_OFF` (Then `POWERING_ON` -> `VERIFYING_POST`. BF counter might persist or reset depending on device).
    3.  **Event (Device):** `last_try_login_attempted_in_tier1` (If applicable, from `DEF_BRUTE_FORCE_1_TRIGGER_DETAILS`)
        *   (Leads to `AWAITING_PIN_INPUT` with special context, then `AWAITING_UNLOCK_CONFIRMATION`)
        *   If this last try fails: It could trigger `USER_RESET (FACTORY_DEFAULT)` or transition to `BRUTE_FORCE_TIER2_LOCKOUT_DETECTED`.
            *   `self.initiate_factory_reset(source_state='BRUTE_FORCE_TIER1_LAST_FAIL_NO_PL')` if `!at.is_provision_lock_enabled()`
            *   Else (if it escalates to Tier 2): `self.to_BRUTE_FORCE_TIER2_LOCKOUT_DETECTED()`

---
**State: `BRUTE_FORCE_TIER2_LOCKOUT_DETECTED`**
*   **Description:** Device showing Tier 2 Brute Force lockout LEDs. Outcome depends on Provision Lock.
*   **Entry Actions:**
    *   `at.confirm_led_pattern(LEDs['BRUTE_FORCED_TIER2_PATTERN'])`
    *   Log "Brute Force Tier 2 Lockout detected."
    *   `is_pl_enabled = at.is_provision_lock_enabled()`
*   **Transitions Out:**
    1.  **Event (Internal):** `tier2_lockout_provision_lock_enabled`
        *   **Condition(s):** `is_pl_enabled == True`.
        *   **Next State:** `DEVICE_BRICKED_AWAITING_ADMIN_RECOVERY_PIN`
    2.  **Event (Internal):** `tier2_lockout_provision_lock_disabled_initiating_reset`
        *   **Condition(s):** `is_pl_enabled == False`.
        *   **Next State:** `INITIATING_FACTORY_RESET` (Payload: `source_state='BRUTE_FORCE_TIER2_NO_PL'`)

---
**State: `DEVICE_BRICKED_AWAITING_ADMIN_RECOVERY_PIN`**
*   **Description:** Device is bricked (BF Tier 2 + Provision Lock). Only Admin Recovery PIN might save it.
*   **Entry Actions:**
    *   `at.confirm_led_solid(LEDs['DEVICE_BRICKED_AWAIT_RECOVERY_PATTERN'], timeout=10)`
    *   Log "Device bricked. Awaiting Admin Recovery PIN."
    *   `self.admin_recovery_attempts = 0`
*   **Transitions Out:**
    1.  **Event (Automation):** `submit_admin_recovery_pin` (Payload: `recovery_pin_sequence`)
        *   `self.admin_recovery_attempts += 1`
        *   `at.sequence(payload['recovery_pin_sequence'])`
        *   `is_recovery_accepted = at.await_led_state(LEDs['FACTORY_RESET_START_AFTER_RECOVERY_PATTERN'] or LEDs['ACCEPT_PATTERN'], timeout=10)`
        *   `is_recovery_rejected = False`
        *   If not `is_recovery_accepted`: `is_recovery_rejected = at.confirm_led_pattern(LEDs['REJECT_PATTERN'], clear_buffer=False)`
        *   If `is_recovery_accepted`: `self.admin_recovery_successful()`
        *   Else if `is_recovery_rejected` AND `self.admin_recovery_attempts < MAX_ADMIN_RECOVERY_ATTEMPTS`: `self.admin_recovery_pin_rejected_retry()`
        *   Else (`is_recovery_rejected` AND attempts exhausted): `self.admin_recovery_failed_permanently_bricked()`
    2.  **Event (Internal):** `admin_recovery_successful`
        *   **Next State:** `INITIATING_FACTORY_RESET` (Payload: `source_state='ADMIN_RECOVERY_SUCCESS'`)
    3.  **Event (Internal):** `admin_recovery_pin_rejected_retry`
        *   **Next State:** `DEVICE_BRICKED_AWAITING_ADMIN_RECOVERY_PIN` (Stays to allow more attempts)
    4.  **Event (Internal):** `admin_recovery_failed_permanently_bricked`
        *   **Next State:** `DEVICE_PERMANENTLY_BRICKED_DETECTED`
    5.  **Event (Automation):** `request_power_off_from_bricked_state`
        *   **Next State:** `POWERING_OFF` (Device should remain bricked on next power on)

---
**State: `DEVICE_PERMANENTLY_BRICKED_DETECTED`**
*   **Description:** Device LEDs indicate it's unrecoverable.
*   **Entry Actions:**
    *   `at.confirm_led_solid(LEDs['PERMANENTLY_BRICKED_PATTERN'], timeout=10)`
    *   Log "DEVICE PERMANENTLY BRICKED. No further automated actions possible."
*   **Transitions Out:**
    1.  **Event (Automation):** `acknowledge_permanent_brick_and_power_off`
        *   **Next State:** `POWERING_OFF`

---
**State: `INITIATING_FACTORY_RESET`**
*   **Description:** Factory Reset command issued (from Admin, Brute Force, Self-Destruct, OOB, Standby), awaiting process start.
*   **Entry Actions (Payload: `source_state`):**
    *   Log "Factory Reset initiated from {event_data.kwargs['source_state']}."
    *   Device should show feedback then start reset. `at.await_led_state(LEDs['FACTORY_RESET_IN_PROGRESS_PATTERN'], timeout=10)`
*   **Transitions Out:**
    1.  **Event:** `factory_reset_process_started`
        *   **Next State:** `FACTORY_RESET_IN_PROGRESS`
    2.  **Event:** `factory_reset_start_failed`
        *   **Next State:** `AUTOMATION_ERROR_STATE` (or `DEVICE_PERMANENTLY_BRICKED_DETECTED` if reset is critical)

---
**State: `FACTORY_RESET_IN_PROGRESS`**
*   **Description:** Observing Factory Reset LED pattern.
*   **Entry Actions:**
    *   `at.confirm_led_pattern(LEDs['FACTORY_RESET_IN_PROGRESS_PATTERN'])`
    *   Log "Factory Reset in progress. Awaiting completion and OOB mode."
    *   Start long timer (e.g., 1-2 minutes).
*   **Transitions Out:**
    1.  **Event:** `factory_reset_completed_oob_detected`
        *   **Condition(s):** `at.await_led_state(LEDs['OOB_MODE_PATTERN'] or LEDs['STANDBY_MODE'], timeout=LONG_RESET_TIMEOUT)` indicating reset finished, device likely in OOB.
        *   **Next State:** `VERIFYING_POST` (as device usually reboots and goes through POST after reset) or directly to `DEVICE_IN_OOB_MODE` if POST is implicitly confirmed by OOB pattern.
    2.  **Event:** `factory_reset_failed_or_timeout`
        *   **Next State:** `AUTOMATION_ERROR_STATE` or `DEVICE_PERMANENTLY_BRICKED_DETECTED`.

---
**State: `SELF_DESTRUCT_SEQUENCE_ACTIVE_WIPING`**
*   (As previously defined, leading to `FACTORY_RESET_IN_PROGRESS` or `DEVICE_IN_OOB_MODE` or error state)

---
**State: `AWAITING_DIAGNOSTIC_MODE_ENTRY`**
*   **Description:** Diagnostic mode entry sequence sent, awaiting confirmation.
*   **Entry Actions:**
    *   `is_diag_ok = at.await_led_state(LEDs['DIAGNOSTIC_MODE_VERSION_DISPLAY_PATTERN'], timeout=10)`
*   **Transitions Out:**
    1.  **Event:** `diagnostic_mode_entry_successful`
        *   **Condition(s):** `is_diag_ok == True`.
        *   **Next State:** `DIAGNOSTIC_MODE_DISPLAYING_INFO`
    2.  **Event:** `diagnostic_mode_entry_failed`
        *   **Next State:** (Source state, e.g., `DEVICE_IN_OOB_MODE` or `DEVICE_IN_STANDBY_MODE`, log error)

---
**State: `DIAGNOSTIC_MODE_DISPLAYING_INFO`**
*   **Description:** Device is displaying version/ID info. Automation might try to capture this or wait.
*   **Entry Actions:**
    *   Log "Diagnostic Mode: Observing version/ID display."
    *   Wait for a fixed duration or specific LED change indicating end of info display.
    *   `at.await_led_state(LEDs['DIAGNOSTIC_KEYPAD_TEST_PROMPT_PATTERN'], timeout=20)`
*   **Transitions Out:**
    1.  **Event:** `diagnostic_info_display_complete_await_keypad_test`
        *   **Next State:** `DIAGNOSTIC_MODE_KEYPAD_TEST_ACTIVE`
    2.  **Event:** `exit_diagnostic_mode_requested_during_info` (If a key press exits)
        *   **Next State:** (Source state, e.g. `DEVICE_IN_OOB_MODE` or `DEVICE_IN_STANDBY_MODE`)
    3.  **Event:** `diagnostic_mode_timeout_or_error`
        *   **Next State:** `AUTOMATION_ERROR_STATE`

---
**State: `DIAGNOSTIC_MODE_KEYPAD_TEST_ACTIVE`**
*   **Description:** Keypad test is active within Diagnostics. Automation can press keys and observe feedback.
*   **Entry Actions:** Log "Diagnostic Mode: Keypad test active."
*   **Internal Actions/Events Handled:**
    *   **Event (Automation):** `test_diagnostic_keypad_button` (Payload: `key_to_press`, `expected_led_feedback_for_key`)
        *   `at.press(payload['key_to_press'])`
        *   `at.confirm_led_pattern(payload['expected_led_feedback_for_key'])` (Log pass/fail for this key)
*   **Transitions Out:**
    1.  **Event (Automation):** `exit_diagnostic_mode_after_keypad_test`
        *   `at.sequence(config.DIAGNOSTIC_EXIT_KEYS)`
        *   **Next State:** (Source state, e.g. `DEVICE_IN_OOB_MODE` or `DEVICE_IN_STANDBY_MODE` after confirming exit pattern)
    2.  **Event (Device Timeout):** `diagnostic_keypad_test_timeout` (If device auto-exits)
        *   **Next State:** (Source state)

---
**State: `DEVICE_IN_SLEEP_MODE` & `AWAKENING_FROM_SLEEP`**
*   **Description:** For devices that support a distinct sleep mode controllable/detectable by automation.
*   **`DEVICE_IN_SLEEP_MODE` Entry:** `at.confirm_led_solid(LEDs['SLEEP_MODE'], ...)`
*   **`DEVICE_IN_SLEEP_MODE` Transitions Out:**
    1.  **Event (Automation):** `wake_device_from_sleep`
        *   `at.press(config.WAKE_KEY)` (or any key if it wakes)
        *   **Next State:** `AWAKENING_FROM_SLEEP`
*   **`AWAKENING_FROM_SLEEP` Entry:** Awaiting Standby or previous active state.
    *   `at.await_led_state(LEDs['STANDBY_MODE'], timeout=5)`
*   **`AWAKENING_FROM_SLEEP` Transitions Out:**
    1.  **Event:** `device_awake_standby_confirmed` -> `DEVICE_IN_STANDBY_MODE`
    2.  **Event:** `device_awaken_failed` -> `AUTOMATION_ERROR_STATE`

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
*   `at.get_brute_force_attempt_counter()` -> int (Hypothetical)
    *   *Usage:* More precise Brute Force handling.
*   `at.get_min_pin_length_setting()` -> int (Hypothetical)

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

This exhaustive document should now cover all the features outlined in `device_markdown_map.md` from an automation FSM perspective. Remember that actual implementation would require defining all the placeholder `LEDs[...]` patterns and `config...._KEYS` sequences.