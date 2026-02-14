# Copyright (c) 2023-2026yes  - Lee Hetherington <lee@edgenative.net>
# Script: junos-irrupdater.py

from jnpr.junos import Device
from jnpr.junos.utils.config import Config
import os
import json
import difflib
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

path = "/usr/share/junos-irrupdater"

def normalize_policy_content(policy_content, ignore_first_last_lines=False):
    # Normalize the indentation and formatting, also allow us to ignore the first and last 2 lines of the text file
    lines = policy_content.strip().split('\n')
    if ignore_first_last_lines and len(lines) > 4:
        lines = lines[2:-2]
    return '\n'.join(line.strip() for line in lines)

def apply_policy(router, policy_name, policy_content, delete_first=False):
    # Apply a policy on the router using configure exclusive.
    # If delete_first is True, removes the existing policy before loading the new one.
    with Config(router, mode='exclusive') as cu:
        if delete_first:
            hierarchy_path = f'policy-options policy-statement {policy_name}'
            cu.load(f'delete {hierarchy_path}', format="set")
        cu.load(policy_content, format="text")
        cu.commit(timeout=360)

def update_policy_statements(router, hostname, policy_files_directory, filter_name, email_config):
    # Process all policy files matching the filter, comparing them against the router config
    # and inserting/updating as needed. Uses configure exclusive to avoid conflicts.
    send_updates = email_config.get("send_updates", False)
    send_errors = email_config.get("send_errors", False)
    smtp_server = email_config.get("smtp_server", "")
    sender_email = email_config.get("sender_email", "")
    receiver_email = email_config.get("receiver_email", "")

    for filename in os.listdir(policy_files_directory):
        if not (filename.endswith(".txt") and filename.startswith(filter_name)):
            continue

        policy_name = filename.split(".")[0]
        print(f"Checking policy {policy_name}...")

        with open(os.path.join(policy_files_directory, filename), 'r') as file:
            policy_content = file.read()

        normalized_policy_content = normalize_policy_content(policy_content, ignore_first_last_lines=True)

        hierarchy_path = f'policy-options policy-statement {policy_name}'
        router_config = router.cli(f'show configuration {hierarchy_path}').strip()

        if not router_config:
            # Policy doesn't exist on router — insert it
            action = "insert"
            action_past = "Inserted"
            email_action = "Added"
            delete_first = False
            print(f"Policy hierarchy for {policy_name} does not exist on the router.")
            print("Inserting policy...")
        else:
            normalized_router_config = normalize_policy_content(router_config)

            if normalized_policy_content == normalized_router_config:
                print(f"Policy Statement {policy_name} is up to date.")
                continue

            # Policy exists but differs — show diff and update
            action = "update"
            action_past = "Updated"
            email_action = "Updated"
            delete_first = True
            print(f"Policy content for {filename} differs from router config.")
            print("Difference:")
            diff = difflib.unified_diff(
                normalized_router_config.splitlines(),
                normalized_policy_content.splitlines(),
                fromfile="router",
                tofile="file",
                lineterm=""
            )
            for line in diff:
                print(line)
            print("Deleting and updating policy...")

        try:
            apply_policy(router, policy_name, policy_content, delete_first=delete_first)
            print(f"{action_past} policy {policy_name} from {filename}")
            if send_updates:
                send_email(smtp_server, sender_email, receiver_email,
                           f"{email_action} Routing Policy {policy_name} on {hostname}")
        except Exception as e:
            print(f"Error during {action} of {policy_name}: {e}")
            if send_errors:
                send_email(smtp_server, sender_email, receiver_email,
                           f"Error during {action} of {policy_name}: {e} on {hostname}")

def send_email(smtp_server, sender_email, receiver_email, message):
    subject = "Routing Policy Update Notification"

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg.attach(MIMEText(message, "plain"))

    with smtplib.SMTP(smtp_server) as server:
        server.sendmail(sender_email, receiver_email, msg.as_string())

def main():
    if len(sys.argv) != 3:
        print("Usage: python junos-irrupdater.py <hostname> <filtername>")
        sys.exit(1)
    hostname = sys.argv[1]
    filter_name = sys.argv[2]
    print("----------------------------------------------------------")
    print(f"Hostname: {hostname}")

    with open(f"{path}/config/routers.conf", "r") as config_file:
        router_info = json.load(config_file)
        router_info["host"] = hostname

    with open(f"{path}/config/email.conf", "r") as email_config_file:
        email_config = json.load(email_config_file)

    policy_files_directory = f"{path}/filters"

    router = Device(**router_info)
    router.open()
    try:
        update_policy_statements(router, hostname, policy_files_directory, filter_name, email_config)
    finally:
        router.close()

if __name__ == "__main__":
    main()
