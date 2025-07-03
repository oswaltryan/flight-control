import subprocess
import os
import json

DISK_TESTER_PATH = r"C:\Users\AKlein.APR1\disk_reliability\target\release\disk_tester.exe"

# test parameters for full-test
TEST_FILE_PATH = r"D:\gemini_disk_test.tmp"
TEST_SIZE = "1G"
BLOCK_SIZE = "4M"
THREADS = "2"
BATCH_SIZE = "1G"
PREALLOCATE = "--preallocate"
DIRECT_IO = "--direct-io"

def run_disk_test(test_type, command_args):
    command = [DISK_TESTER_PATH, test_type] + command_args
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
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"[{test_type.capitalize()} test failed] Exit code: {e.returncode}")
        print("STDOUT:\n", e.stdout)
        print("STDERR:\n", e.stderr)
    except FileNotFoundError:
        print(f"Error: disk_tester.exe not found at {DISK_TESTER_PATH}")
    except Exception as e:
        print(f"Unexpected error during {test_type} test: {e}")
    return None

def run_full_test(path, test_size, block_size, threads, batch_size, preallocate, direct_io, data_type=None, dual_pattern=False):
    command_args = [
        "--path", path,
        "--test-size", test_size,
        "--block-size", block_size,
        "--threads", threads,
        "--batch-size", batch_size,
    ]
    if preallocate:
        command_args.append(preallocate)
    if direct_io:
        command_args.append(direct_io)
    if dual_pattern:
        command_args.append("--dual-pattern")
    elif data_type:
        command_args.extend(["--data-type", data_type])
    
    run_disk_test("full-test", command_args)

def run_bench_test(path, mode, direct_io=False):
    command_args = [
        "--path", path,
        "--mode", mode,
        "--json",
    ]
    if direct_io:
        command_args.append("--direct-io")
    
    stdout = run_disk_test("bench", command_args)
    if stdout:
        try:
            json_output = json.loads(stdout)
            print("\nJSON Output:")
            print(json.dumps(json_output, indent=4))
        except json.JSONDecodeError:
            print("\nFailed to decode JSON output.")


# Execute
if __name__ == "__main__":


    # Example of running bench tests
    run_bench_test(path="D:", mode="seq1m-q8t1", direct_io=True)
    run_bench_test(path="D:", mode="seq1m-q8t1", direct_io=False)

    # cleanup
    try:
        if os.path.exists(TEST_FILE_PATH):
            os.remove(TEST_FILE_PATH)
            print(f"\nCleaned up test file: {TEST_FILE_PATH}")
    except OSError as e:
        print(f"Error deleting test file {TEST_FILE_PATH}: {e}")