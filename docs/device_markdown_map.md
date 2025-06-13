# APRICORN DEVICE DOCUMENT

## DEFINITIONS LIBRARY
This section provides the detailed structure for reusable component blocks. These blocks are referenced by their keys in the main "APRICORN DEVICE MAP" below. The keys define the *content* or *sub-structure* of the named mode/event.

---

### #DEF_ADMIN_MODE_CONTENTS
  - ENROLL (PIN/COUNTER)
    - ENROLL USER PIN
    - BRUTE FORCE COUNTER
    - CHANGE ADMIN PIN
    - ENROLL SELF-DESTRUCT PIN
    - MIN PIN LENGTH COUNTER
    - ENROLL RECOVERY PIN (4)
  - TOGGLE (FEAUTRE)
    - BASIC DISK
    - DELETE PINS
    - LED FLICKER
    - LOCK OVERRIDE
    - PROVISION LOCK
    - READ ONLY
    - READ WRITE
    - REMOVABLE MEDIA
    - SELF-DESTRUCT PIN
    - UNATTENDED AUTO LOCK
    - USER FORCED ENROLLMENT
  - USER RESET (FACTORY DEFAULT) (IF NOT PROVISION LOCK)
    - (Device enters OOB MODE)

---

### #DEF_BRUTE_FORCE_1_TRIGGER_DETAILS
  - LAST TRY LOGIN
  - USER RESET (FACTORY DEFAULT) (IF NOT PROVISION LOCK)
    - (Device enters OOB MODE)

---

### #DEF_BRUTE_FORCE_2_TRIGGER_DETAILS
  - BRICKED STATE (IF PROVISION LOCK ENABLED) # Device enters this state
    - ADMIN RECOVER LOGIN (Action from Bricked State to attempt recovery)
      - IF LOGIN SUCCEEDS:
        - USER RESET (FACTORY DEFAULT)
          - (Device enters OOB MODE)
      - IF LOGIN FAILS 5x:
        - PERMANENTLY BRICKED # Final state after failed recovery attempts
  - USER RESET (FACTORY DEFAULT) (IF PROVISION LOCK NOT ENABLED) # Alternative path
    - (Device enters OOB MODE)

---

### #DEF_USER_UNLOCKED_SUB_OPTIONS
  - CHANGE USER PIN
  - ENROLL SELF-DESTRUCT PIN

---
---

## APRICORN DEVICE MAP
This section outlines the operational flow and states of the Apricorn Device.

- SLEEP MODE
  - WAKE (NO SELF-TEST) OR STARTUP (SELF-TEST)
    - OOB MODE
      - ENROLL ADMIN PIN
        - ADMIN MODE
          - (Contents Ref: #DEF_ADMIN_MODE_CONTENTS)
      - DIAGNOSTIC MODE
      - USER RESET (FACTORY DEFAULT) (IF NOT PROVISION LOCK)
        - (Device re-initializes / remains in OOB MODE)

    - USER-FORCED ENROLLMENT
      - ADMIN UNLOCK
      - ADMIN MODE LOGIN
         - ADMIN MODE
           - (Contents Ref: #DEF_ADMIN_MODE_CONTENTS)
      - BRUTE FORCE (1ST TRIGGER) # An event/state that can occur during PIN attempts
        - (Details Ref: #DEF_BRUTE_FORCE_1_TRIGGER_DETAILS)
      - BRUTE FORCE (2ND TRIGGER) # An event/state that can occur during PIN attempts
        - (Details Ref: #DEF_BRUTE_FORCE_2_TRIGGER_DETAILS)
      - ENROLL USER PIN
      - DIAGNOSTIC MODE
      - SELF-DESCTRUCT UNLOCK
      - USER RESET (FACTORY DEFAULT) (IF NOT PROVISION LOCK)
        - (Device enters OOB MODE)
      - USER UNLOCK

    - STANDBY MODE
      - ADMIN MODE LOGIN
         - ADMIN MODE
           - (Contents Ref: #DEF_ADMIN_MODE_CONTENTS)
      - ADMIN UNLOCKED # Data accessible with Admin PIN
      - BASIC DISK | REMOVABLE DISK (TOGGLE) # Verify with PDF if keeping
      - BRUTE FORCE (1ST TRIGGER) # An event/state that can occur
        - (Details Ref: #DEF_BRUTE_FORCE_1_TRIGGER_DETAILS)
      - BRUTE FORCE (2ND TRIGGER) # An event/state that can occur
        - (Details Ref: #DEF_BRUTE_FORCE_2_TRIGGER_DETAILS)
      - DIAGNOSTIC MODE
      - ENROLL SELF-DESTRUCT PIN # Context needs PDF alignment (Admin vs User)
      - READ ONLY | READ WRITE
        - ADMIN UNLOCKED
        - USER UNLOCKED
          - (Sub-options Ref: #DEF_USER_UNLOCKED_SUB_OPTIONS)
      - RECOVERY PIN LOGIN
      - SELF-DESTRUCT UNLOCK
      - USER RESET (FACTORY DEFAULT) (IF NOT PROVISION LOCK)
        - (Device enters OOB MODE)
      - USER UNLOCKED
        - (Sub-options Ref: #DEF_USER_UNLOCKED_SUB_OPTIONS)

    - BRUTE FORCE (1ST TRIGGER)
      - (Details Ref: #DEF_BRUTE_FORCE_1_TRIGGER_DETAILS)
    - BRUTE FORCE (2ND TRIGGER)
      - (Details Ref: #DEF_BRUTE_FORCE_2_TRIGGER_DETAILS)