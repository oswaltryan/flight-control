# Dictionaries ------------------------------------------------------------------- #

# LEDs --------------------------------- #

## This dictionary contains ALL LED patterns and state that will be used for testing.
LEDs = {

# Single-Line Patterns ----------------- #
## The patterns below are single-line patterns, meaning there is only one pattern to match.
## Put differently, there is only a state to match and not a pattern.

    'AUTOLOCK_5_STATE':         {'red':0, 'green':1, 'blue':0, 'duration': (280,    315)}, ## pattern match = 05 minutes
    'AUTOLOCK_10_STATE':        {'red':0, 'green':1, 'blue':0, 'duration': (580,    630)}, ## pattern match = 10 minutes 12 seconds
    'AUTOLOCK_20_STATE':        {'red':0, 'green':1, 'blue':0, 'duration': (1180,  1245)}, ## pattern match = 20 minutes 40 seconds

    ## pattern match = 03 seconds
    'ACCEPT_STATE':             {'red':0, 'green':1, 'blue':0},
    'ADMIN_MODE':               {'red':0, 'green':0, 'blue':1},
    'ALL_OFF':                  {'red':0, 'green':0, 'blue':0},
    'ALL_ON':                   {'red':1, 'green':1, 'blue':1},
    'FW_VERSION':               {'red':0, 'green':0, 'blue':0},
    'DIAGNOSTIC_MODE':          {'red':0, 'green':0, 'blue':1},
    'DIAGNOSTIC_MODE_TIMEOUT':  [0],
    'CONFIRMATION':             {'red':0, 'green':1, 'blue':0},
    'GREEN_BLUE_STATE':         {'red':0, 'green':1, 'blue':1},
    'KEY_GENERATION':           {'red':1, 'green':1, 'blue':0},
    'KEY_GENERATION_LEGACY':    {'red':1, 'green':1, 'blue':0},
    'SLEEP_MODE':               {'red':0, 'green':0, 'blue':0},
    'STABLE_ENUM':              {'red':0, 'green':1, 'blue':0},
    'STANDBY_MODE':             {'red':1, 'green':0, 'blue':0},
    'RED_ONLY':                 {'red':1, 'green':0, 'blue':0},
    'GREEN_ONLY':               {'red':0, 'green':1, 'blue':0},
    'BLUE_ONLY':                {'red':0, 'green':0, 'blue':1},


# Complex Patterns --------------------- #
## The patterns below are actual patterns, meaning there are multiple lines to match.
## These patterns will work with legacyProduct(s) and non legacyProduct(s).

    'ACCEPT_PATTERN':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.08,  0.6)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.6)}],

    'ACCEPT_PATTERN_INCOMPLETE':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  0.6)}],

    ## This pattern is used for PIC dev firmware meant to test the Initio chip.
    'BLUE': [
        {'red':0, 'green':0, 'blue': 1, 'duration': (0,     0.35)},
        {'red':0, 'green':0, 'blue': 0, 'duration': (0.05,  0.35)},
        {'red':0, 'green':0, 'blue': 1, 'duration': (0.05,  0.35)},
        {'red':0, 'green':0, 'blue': 0, 'duration': (0.05,  0.35)},
        {'red':0, 'green':0, 'blue': 1, 'duration': (0.05,  0.40)},
        {'red':0, 'green':0, 'blue': 0, 'duration': (0.05,  0.35)}],

    'BRUTE_FORCED':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  1.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.02,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.02,  0.30)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.05,  0.30)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  0.30)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.05,  0.30)}],

    'ENUM':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  3.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.05,  0.6)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  1.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.05,  0.6)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  0.6)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.05,  0.6)}],

    'ENUM_LEGACY':  [
        {'red':0, 'green':1, 'blue':0, 'duration': (4.00, 12.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  1.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.05,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  1.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.05,  4.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  1.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.05,  1.0)}],

    ## Per the SABRI code there should be no difference between unlocking the device or logging into Admin mode but there is a subtle difference in both that manifests itself more when unlocking while VBUS is applied.
    ## Otherwise for both unlocking and logging into Admin mode with the 'self_destruct_pin' requires about 5-7 seconds of wait time after the PIN is entered to allow for clearing of PINs and data on the device in the background.
    'ENUM_SELF_DESTRUCT':  [
        {'red':0, 'green':1, 'blue':0, 'duration': (4.0,   7.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  0.7)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.05,  0.7)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  0.7)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.05,  5.0)}],

    'ENUM_LOCK_OVERRIDE':  [
    #	{'red':0, 'green':1, 'blue':0, 'duration': (0.00, 15.0)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.00,  5.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (2.50,  3.5)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.20,  0.7)},
        {'red':0, 'green':1, 'blue':0, 'duration': (2.50,  3.5)}],

    'ENUM_LOCK_OVERRIDE_READ_ONLY':  [
    #	{'red':0, 'green':1, 'blue':0, 'duration': (0.00,  5.0)},
        {'red':1, 'green':1, 'blue':0, 'duration': (0.00, 10.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (1.00,  2.0)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.15,  0.7)},
        {'red':0, 'green':1, 'blue':0, 'duration': (1.00,  2.0)},
        {'red':1, 'green':1, 'blue':0, 'duration': (0.15,  0.7)},
        {'red':0, 'green':1, 'blue':0, 'duration': (1.00,  2.0)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.15,  0.7)}],

    'ENUM_READ_ONLY':  [
    #	{'red':0, 'green':1, 'blue':0, 'duration': (0.0,   5.0)},
        {'red':1, 'green':1, 'blue':0, 'duration': (0.0,   5.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (2.0,   3.5)},
        {'red':1, 'green':1, 'blue':0, 'duration': (0.2,   1.2)},
        {'red':0, 'green':1, 'blue':0, 'duration': (2.0,   3.5)}],

    ## pattern match:  05 seconds
    ## This pattern is used for errorState.
    'ERROR_STATE':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  1.35)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  1.35)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.50,  1.35)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.50,  1.35)}],

    'FIRST_KEY_KEYPAD_TEST': [
        {'red':0, 'green':0, 'blue':1, 'duration':  (0.01,  0.5)},
        {'red':0, 'green':1, 'blue':0, 'duration':  (0.01,  0.5)}],

    'FLICKER_BLUE':  [
        {'red':0, 'green':0, 'blue':1, 'duration': (0.00,  3.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.01,  0.8)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.01,  0.8)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.01,  0.8)}],

    'FLICKER_GREEN':  [
        {'red':0, 'green':1, 'blue':0, 'duration': (0.00,  3.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.8)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.01,  0.8)}],

    'FLICKER_RED':  [
        {'red':1, 'green':0, 'blue':0, 'duration': (0.00,  3.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.7)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  0.7)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.7)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  0.7)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.7)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.01,  0.7)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  0.7)}],

    ## pattern match:  05 seconds
    'GREEN_BLUE':  [
        {'red':0, 'green':0, 'blue':1, 'duration': (0.00,  1.0)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.05,  1.0)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.05,  0.7)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.20,  0.7)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.10,  0.7)}],

    ## pattern match:  10 seconds
    'OOB_CHARGE':  [{'green':1, 'blue':1, 'duration': (3.00,  7.0)}],

    # ## pattern match:  10 seconds
    # 'OOB_CHARGE':  [
    #     {'red':1, 'green':1, 'blue':1, 'duration': (0.00,  7.0)},
    #     {'red':0, 'green':1, 'blue':1, 'duration': (0.05,  1.0)},
    #     {'red':1, 'green':1, 'blue':1, 'duration': (3.00,  7.0)},
    #     {'red':0, 'green':1, 'blue':1, 'duration': (0.05,  1.0)},
    #     {'red':1, 'green':1, 'blue':1, 'duration': (3.00,  7.0)}],

    ## pattern match:  05 seconds
    ## This pattern is used for provisionLockBricked.
    'PROVISION_LOCK_BRICKED':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  1.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.50,  1.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.50,  1.0)}],

    ## This pattern is used for bruteForceEnrollment and minPINCountEnrollment.
    'RED_COUNTER': [
        {'red':0, 'green':0, 'blue': 0, 'duration': (0,     1.9)},
        {'red':1, 'green':0, 'blue': 0, 'duration': (0.05,  0.6)},
        {'red':0, 'green':0, 'blue': 0, 'duration': (0.05,  1.9)},
        {'red':1, 'green':0, 'blue': 0, 'duration': (0.05,  0.6)},
        {'red':0, 'green':0, 'blue': 0, 'duration': (0.05,  1.9)}],

    ## pattern match:  05 seconds
    ## This pattern is used for adminLogin, loginRecovery and changeLoginUser.
    'RED_LOGIN':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  1.9)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  2.1)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.90,  1.9)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.90,  1.9)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.90,  1.9)}],

    ## pattern match:  05 seconds
    ## This pattern is used for enrollmentSelfDestruct, enrollmentUnattendedAutoLock, and userResetWarning
    'RED_BLUE':  [
        {'red':1, 'green':0, 'blue':0, 'duration': (0.00,  1.0)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.01,  1.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  0.7)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.10,  0.7)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  0.7)}],

    ## pattern match:  10 seconds
    'RED_GREEN':  [
        {'red':0, 'green':1, 'blue':0, 'duration': (0.00,  1.1)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.05,  1.1)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.40,  1.1)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.40,  1.1)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.40,  1.1)}],

    ## pattern match:  03 seconds
    'RED_GREEN_BLUE':  [
#       {'red':0, 'green':0, 'blue':1, 'duration': (0.00,  2.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.00,  4.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.50,  2.3)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.01,  2.3)}],
#       {'red':1, 'green':0, 'blue':0, 'duration': (0.05,  2.0)},
#       {'red':0, 'green':1, 'blue':0, 'duration': (1.00,  2.0)}],

    'REJECT':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  1.1)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.4)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  0.4)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.4)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  0.4)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.4)}],

    ## pattern match:  10 seconds
    'STANDBY_CHARGE':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0,    30.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (2.00, 30.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05, 30.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (2.00, 30.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05, 30.0)}],

    ## pattern match:  05 seconds
    ## This pattern is used for enrollmentSelfDestruct, enrollmentUnattendedAutoLock, and userResetWarning
    'USER_RESET_KEY':  [
        {'green':0, 'blue':0, 'duration': (0.00,  1.0)},
        {'green':0, 'blue':1, 'duration': (0.01,  1.0)},
        {'green':0, 'blue':0, 'duration': (0.10,  0.7)},
        {'green':0, 'blue':1, 'duration': (0.10,  0.7)},
        {'green':0, 'blue':0, 'duration': (0.10,  0.7)}],

}

## This dictionary contains ALL the LED patterns used for DUT.modeOrientation()
## Enrollments go first because 
ORIENTATION_LEDs = {
    'ALL_ON':                   [{'red':1, 'green':1, 'blue':1, 'duration': (3.00,   5.0)}],
    'RED_BLUE':  [
        {'red':1, 'green':0, 'blue':0, 'duration': (0.00,  1.0)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.01,  1.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  0.7)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.10,  0.7)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  0.7)}],
    'GREEN_BLUE':  [
        {'red':0, 'green':0, 'blue':1, 'duration': (0.00,  1.0)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.05,  1.0)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.05,  0.7)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.20,  0.7)},
        {'red':0, 'green':0, 'blue':1, 'duration': (0.10,  0.7)}],
    'ADMIN_MODE':               [{'red':0, 'green':0, 'blue':1, 'duration': (3.00,   5.0)}],
    'ENUM_STATE':               [{'red':0, 'green':1, 'blue':0, 'duration': (3.00,   5.0)}],
    'ERROR_STATE':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  1.35)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  1.35)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.50,  1.35)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.50,  1.35)}],
    'GREEN_BLUE_STATE':         [{'red':0, 'green':1, 'blue':1, 'duration': (3.00,   5.0)}],
    'KEY_GENERATION':           [{'red':1, 'green':1, 'blue':0, 'duration': (1.00,   5.0)}],
    'STANDBY_MODE':             [{'red':1, 'green':0, 'blue':0, 'duration': (3.00,   5.0)}],
    'STANDBY_CHARGE':  [
        {'red':1, 'green':0, 'blue':0, 'duration': (0.00, 30.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05, 30.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (2.00, 30.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05, 30.0)}],
    'BRUTE_FORCED':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  1.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.02,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.02,  0.5)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.05,  0.5)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.05,  0.5)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.05,  0.5)}],
    'SLEEP_MODE':               [{'red':0, 'green':0, 'blue':0, 'duration': (2.00,   5.0)}],
}

ORIENT_ACCEPT_REJECT_LEDs = {
    'ACCEPT_PATTERN':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.6)}],

    'ACCEPT_PATTERN_INCOMPLETE':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':0, 'green':1, 'blue':0, 'duration': (0.10,  0.6)}],

    'KEY_GENERATION':           [{'red':1, 'green':1, 'blue':0, 'duration': (1.00,   5.0)}],


    'REJECT':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.4)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  0.4)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.4)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  0.4)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.4)}],

    'REJECT_PATTERN_INCOMPLETE':  [
        {'red':0, 'green':0, 'blue':0, 'duration': (0.00,  3.0)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.01,  1.0)},
        {'red':0, 'green':0, 'blue':0, 'duration': (0.10,  0.6)},
        {'red':1, 'green':0, 'blue':0, 'duration': (0.10,  0.6)}],

    'STANDBY_MODE':             [{'red':1, 'green':0, 'blue':0, 'duration': (3.00,   5.0)}],
}

ORIENT_ENUM_LEDs = {
    'STABLE_ENUM':         [{'red':0, 'green':1, 'blue':0, 'duration': (5.00,   7.0)}],
    'ENUM_LOCK_OVERRIDE':  [
    #	{'red':0, 'green':1, 'blue':0, 'duration': (0.00, 15.0)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.00,  5.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (2.50,  3.5)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.20,  0.7)},
        {'red':0, 'green':1, 'blue':0, 'duration': (2.50,  3.5)}],
    'ENUM_LOCK_OVERRIDE_READ_ONLY':  [
    #	{'red':0, 'green':1, 'blue':0, 'duration': (0.00,  5.0)},
        {'red':1, 'green':1, 'blue':0, 'duration': (0.00, 10.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (1.00,  2.0)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.15,  0.7)},
        {'red':0, 'green':1, 'blue':0, 'duration': (1.00,  2.0)},
        {'red':1, 'green':1, 'blue':0, 'duration': (0.15,  0.7)},
        {'red':0, 'green':1, 'blue':0, 'duration': (1.00,  2.0)},
        {'red':0, 'green':1, 'blue':1, 'duration': (0.15,  0.7)}],
    'ENUM_READ_ONLY':  [
    #	{'red':0, 'green':1, 'blue':0, 'duration': (0.0,   5.0)},
        {'red':1, 'green':1, 'blue':0, 'duration': (0.0,   5.0)},
        {'red':0, 'green':1, 'blue':0, 'duration': (2.5,   3.5)},
        {'red':1, 'green':1, 'blue':0, 'duration': (0.2,   0.7)},
        {'red':0, 'green':1, 'blue':0, 'duration': (2.5,   3.5)}]
}

ERROR_STATES = {}