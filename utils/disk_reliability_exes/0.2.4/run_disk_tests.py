import subprocess
import os

DISK_TESTER_PATH = r""

# test parameters
TEST_FILE_PATH = r"D:\gemini_disk_test.tmp"
TEST_SIZE = "1M"
BLOCK_SIZE = "4M"
THREADS = "2"
BATCH_SIZE = "1M"
PREALLOCATE = "--preallocate"
DIRECT_IO = "--direct-io"


def run_disk_test(test_type, path, test_size, block_size, threads, batch_size, preallocate, direct_io, data_type=None, dual_pattern=False):
    command = [
        DISK_TESTER_PATH,
        "full-test",
        "--path", path,
        "--test-size", test_size,
        "--block-size", block_size,
        "--threads", threads,
        "--batch-size", batch_size,
    ]

    if preallocate:
        command.append(preallocate)
    if direct_io:
        command.append(direct_io)
    if dual_pattern:
        command.append("--dual-pattern")
    elif data_type:
        command.extend(["--data-type", data_type])

    print(f"\n[Running {test_type} test]")
    print(f"Command: {' '.join(command)}")
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8',
        )
        print("STDOUT:\n", result.stdout)
        print("STDERR:\n", result.stderr)
        print(f"[{test_type.capitalize()} test completed successfully]")
    except subprocess.CalledProcessError as e:
        print(f"[{test_type.capitalize()} test failed] Exit code: {e.returncode}")
        print("STDOUT:\n", e.stdout)
        print("STDERR:\n", e.stderr)
    except FileNotFoundError:
        print(f"Error: disk_tester.exe not found at {DISK_TESTER_PATH}")
    except Exception as e:
        print(f"Unexpected error during {test_type} test: {e}")

def run_dual_pattern_test():
    run_disk_test(
        test_type="dual-pattern",
        path=TEST_FILE_PATH,
        test_size=TEST_SIZE,
        block_size=BLOCK_SIZE,
        threads=THREADS,
        batch_size=BATCH_SIZE,
        preallocate=PREALLOCATE,
        direct_io=DIRECT_IO,
        dual_pattern=True
    )


# Execute
if __name__ == "__main__":
    run_dual_pattern_test()

   # cleanup
    try:
        if os.path.exists(TEST_FILE_PATH):
            os.remove(TEST_FILE_PATH)
            print(f"\nCleaned up test file: {TEST_FILE_PATH}")
    except OSError as e:
        print(f"Error deleting test file {TEST_FILE_PATH}: {e}")
