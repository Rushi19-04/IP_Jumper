import subprocess
import time
import argparse
import sys
import os
from datetime import datetime


def get_current_ip(verbose=False):
    try:
        env = os.environ.copy()
        if not verbose:
            env["PROXYCHAINS_LOG_LEVEL"] = "0"

        process = subprocess.Popen(
            ['proxychains', 'curl', '-s', 'https://checkip.amazonaws.com'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env
        )
        output, _ = process.communicate()
        lines = output.decode().strip().splitlines()
        return lines
    except Exception as e:
        return [f"Error fetching IP: {e}"]


def run_hops(hops, delay):
    count = 0
    with open("hop_log.txt", "a") as log:
        while True:
            print(f"\n\033[92m[+] Restarting Tor for hop #{count + 1 if hops else count}...\033[0m")
            sys.stdout.flush()

            subprocess.run(['sudo', 'systemctl', 'restart', 'tor'], check=True)
            time.sleep(5)

            output_lines = get_current_ip(verbose=(count == 0))
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if count == 0:
                ip = output_lines[-1]
                
                for line in output_lines[:-1]:
                    print(line)
             
                print(f"\033[91m[+] {timestamp} | Current IP: {ip}\033[0m")

            else:
                ip = output_lines[-1]
                print(f"\033[91m[+] {timestamp} | Current IP: {ip}\033[0m")


            sys.stdout.flush()
            log.write(f"[{timestamp}] Hop #{count + 1 if hops else count}: {ip}\n")

            count += 1
            if hops and count >= hops:
                break

            time.sleep(delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--hops', type=int, required=False, help='Number of IP hops (0 = infinite)')
    parser.add_argument('--delay', type=int, required=False, help='Delay between hops (in seconds)')
    args = parser.parse_args()

    hops = args.hops if args.hops is not None else 0
    delay = args.delay if args.delay is not None else 5

    print("\033[96m===== IP Jumper (VPS) Started =====\033[0m")
    sys.stdout.flush()

    run_hops(hops, delay)

    print("\n✅ All hops completed. Exiting.")
    sys.stdout.flush()
