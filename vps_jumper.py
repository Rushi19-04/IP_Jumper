import boto3
import subprocess
import time
import json
import socket
from datetime import datetime, timezone
import sys 
import os

if os.name == "nt":
    os.system("")

banner = r"""

  ___   ____         _   _   _   _     _   ___     _____   ____  
 |_ _| |  _ \       | | | | | | | |\_/| | | _  \  | ____| |  __ \ 
  | |  | |_) |   _  | | | | | | | |\_/| | | |_) | |  _|   | |__) |
  | |  |  _ /   | |_| | | |_| | | |   | | |  _ /  | |___  |  _ < 
 |___| |_|       \___/   \___/  |_|   |_| |_|     |_____| |_| \_\ 
                                                                 
"""

print("\033[36m")
print(banner)
print("\033[0m")

with open("config.json") as f:
    config = json.load(f)

INSTANCE_ID = config['instance_id']
REGION = config['region']
KEY_PATH = config['pem_key_path']
USERNAME = config['ssh_user']
REMOTE_FILE = "jumper.py"

client = boto3.client('ec2', region_name=REGION)
cloudwatch = boto3.client('cloudwatch', region_name=REGION)

def check_instance_uptime():
    print("[i] Checking EC2 usage for this month...")
    try:
        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/EC2',
            MetricName='CPUUtilization',
            Dimensions=[{'Name': 'InstanceId', 'Value': INSTANCE_ID}],
            StartTime=start_of_month,
            EndTime=now,
            Period=3600,
            Statistics=['SampleCount']
        )
        hours = len(response['Datapoints'])
        print(f"[i] Estimated EC2 hours used this month: {hours}h")
        if hours >= 740:
            print("[!] WARNING: You are close to 750 hour Free Tier limit!")
            confirm = input("Do you still want to continue? (yes/no): ").strip().lower()
            if confirm != 'yes':
                print("[-] Aborting script to avoid AWS charges.")
                exit()
    except Exception as e:
        print(f"[!] Failed to check usage: {e}")

def wait_until_stopped():
    while True:
        state = client.describe_instances(InstanceIds=[INSTANCE_ID])['Reservations'][0]['Instances'][0]['State']['Name']
        if state == 'stopped':
            return True
        elif state in ['stopping', 'shutting-down']:
            print(f"[i] Waiting for instance to stop (currently: {state})...")
            time.sleep(5)
        else:
            return False

def wait_for_ssh(ip, timeout=60):
    print("[*] Waiting for SSH to become available...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.create_connection((ip, 22), timeout=2)
            sock.close()
            print(f"[+] SSH is now available at {ip}:22")
            return
        except:
            print("[i] Waiting for SSH to become ready...")
            time.sleep(5)
    print("[!] SSH did not become ready in time.")
    exit(1)

def start_instance():
    print("[+] Starting EC2 instance...")
    try:
        client.start_instances(InstanceIds=[INSTANCE_ID])
        return True
    except client.exceptions.ClientError as e:
        if "IncorrectInstanceState" in str(e):
            print("[!] Instance not startable right now – checking state...")
            if wait_until_stopped():
                print("[i] Now stopped. Retrying start...")
                client.start_instances(InstanceIds=[INSTANCE_ID])
                return True
            else:
                print("[-] Aborting. Instance is not in a startable state.")
                return False
        else:
            raise e

def get_public_ip(instance_id, ec2):
    print("[i] Waiting for EC2 instance to be assigned a public IP...")
    for _ in range(20):  
        reservations = ec2.describe_instances(InstanceIds=[instance_id])['Reservations']
        instance = reservations[0]['Instances'][0]
        public_ip = instance.get('PublicIpAddress')
        if public_ip:
            print(f"[+] Public IP assigned: {public_ip}")
            return public_ip
        time.sleep(3)
    print("[!] Timeout: Instance did not receive a public IP.")
    exit(1)

def stop_instance():
    print("[+] Stopping EC2 instance...")
    client.stop_instances(InstanceIds=[INSTANCE_ID])
    print("[+] Instance stopped.")

def send_jumper_file(ip):
    print("[+] Sending jumper.py to VPS...")
    subprocess.run([
        'scp', '-o', 'StrictHostKeyChecking=no', '-i', KEY_PATH,
        REMOTE_FILE, f'{USERNAME}@{ip}:~/'
    ], check=True)

def fetch_log_file(ip):
    print("[+] Downloading hop_log.txt from VPS...")
    subprocess.run([
        'scp', '-o', 'StrictHostKeyChecking=no', '-i', KEY_PATH,
        f'{USERNAME}@{ip}:~/hop_log.txt', 'hop_log.txt'
    ], check=True)

def stream_remote_script(ip, hops, delay):
    print("[+] Streaming live output from jumper.py ...")
    ssh = subprocess.Popen([
        'ssh', '-o', 'StrictHostKeyChecking=no', '-i', KEY_PATH,
        f'{USERNAME}@{ip}',
        f'python3 -u {REMOTE_FILE} --hops {hops} --delay {delay}'
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    try:
        for line in ssh.stdout:
            print(line, end="")
    except KeyboardInterrupt:
        print("\n[!] Interrupted. Killing remote process...")
        ssh.kill()

if __name__ == '__main__':
    print("\n===== IP Jumper (Local Controller) =====")

    # Get input from user
    try:
        hops_input = input("Enter number of hops (0 for infinite): ").strip()
        delay_input = input("Enter delay between hops (in seconds, min 5): ").strip()
    except KeyboardInterrupt:
        print("\nExiting…")
        sys.exit(0)

    # Parse input
    hops = int(hops_input) if hops_input else 0
    delay = int(delay_input) if delay_input else 5

    check_instance_uptime()

    if not start_instance():
        exit()

    time.sleep(10)
    
    ip = get_public_ip(INSTANCE_ID, client)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[+] {timestamp} | VPS Public IP: {ip}")

    wait_for_ssh(ip)

    try:
        send_jumper_file(ip)
        stream_remote_script(ip, hops, delay)   # ⬅️ real-time output shown here!
        fetch_log_file(ip)
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user. Cleaning up...")
    finally:
        stop_instance()
        print("\n✅ Jumper completed.")
