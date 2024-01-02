# Copyright (c) 2023-2024 - Lee Hetherington <lee@edgenative.net>
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

def read_router_config_for_policy(router_info, policy_name):
    router = None
    try:
        router = Device(**router_info)
        router.open()
        hierarchy_path = f'policy-options policy-statement {policy_name}'
        router_config = router.cli(f'show configuration {hierarchy_path}')
        return router_config.strip()
    finally:
        if router:
            router.close()

def normalize_policy_content(policy_content, ignore_first_last_lines=False):
    # Normalize the indentation anf formatting, also allow us to ignore the first and last 2 lines of the text file
    lines = policy_content.strip().split('\n')
    if ignore_first_last_lines and len(lines) > 4:
        lines = lines[2:-2]
    normalized_content = '\n'.join(line.strip() for line in lines)
    return normalized_content

def update_policy(router, policy_name, policy_content):
    # Update the policy on the router.  Do this with configure exclusive
    with Config(router, mode='exclusive') as cu:
        hierarchy_path = f'policy-options policy-statement {policy_name}'
        cu.load(f'delete {hierarchy_path}', format="set")
        cu.load(policy_content, format="text")
        cu.commit(timeout=360)

def update_policy_statements(router_info, policy_files_directory, filter_name, email_config):
    # This function deletes the existing policy, then inserts the new policy after which it runs a commit.  We're doing this with configure exclusive
    # to avoid any errors.  Had to have this happen in a single function, as before it wasn't actually deleteting the old policy when there was a change
    # and so it was telling you it had been updated, but then every run detecting a change and never actually inserting it.
    send_updates = email_config.get("send_updates", False)
    send_errors = email_config.get("send_errors", False)

    smtp_server = email_config.get("smtp_server", "")
    sender_email = email_config.get("sender_email", "")
    receiver_email = email_config.get("receiver_email", "")
    hostname = sys.argv[1]

    for filename in os.listdir(policy_files_directory):
        if filename.endswith(".txt") and filename.startswith(filter_name):
            policy_name = filename.split(".")[0]
            print(f"Checking policy {policy_name}...")

            with open(os.path.join(policy_files_directory, filename), 'r') as file:
                policy_content = file.read()

            normalized_policy_content = normalize_policy_content(policy_content, ignore_first_last_lines=True)
            router_config = read_router_config_for_policy(router_info, policy_name)

            if not router_config.strip():
                print(f"Policy hierarchy for {policy_name} does not exist on the router.")
                print("Inserting policy...")
                try:
                    router = Device(**router_info)
                    router.open()
                    update_policy(router, policy_name, policy_content)
                    print(f"Inserted policy {policy_name} from {filename}")

                    if send_updates:
                        send_email(smtp_server, sender_email, receiver_email, f"Added Routing Policy {policy_name} on {hostname}")

                except Exception as e:
                    print(f"Error inserting {policy_name}: {e}")
                    if send_errors:
                        send_email(smtp_server, sender_email, receiver_email, f"Error inserting {policy_name}: {e} on {hostname}")
                finally:
                    if router:
                        router.close()
            else:
                normalized_router_config = normalize_policy_content(router_config)

                if normalized_policy_content.strip() != normalized_router_config.strip():
                    print(f"Policy content for {filename} differs from router config.")
                    print("Difference:")
                    d = difflib.Differ()
                    diff = list(d.compare(
                        normalized_policy_content.splitlines(),
                        normalized_router_config.splitlines()
                    ))
                    for line in diff:
                        if line.startswith('- ') or line.startswith('+ '):
                            print(line)
                    print("Deleting and updating policy...")

                    try:
                        router = Device(**router_info)
                        router.open()
                        update_policy(router, policy_name, policy_content)
                        print(f"Updated policy statement from {filename}")

                        if send_updates:
                             # Send an email upon update if enabled, that includes the policy_name and hostname of the router
                            send_email(smtp_server, sender_email, receiver_email, f"Updated Routing Policy {policy_name} on {hostname}")

                    except Exception as e:
                        print(f"Error updating {policy_name}: {e}")
                        if send_errors:
                            # Send an email upon error if enabled, that includes the policy_name and hostname of the router
                            send_email(smtp_server, sender_email, receiver_email, f"Error updating {policy_name}: {e} on {hostname}")
                    finally:
                        if router:
                            router.close()
                else:
                    print(f"Policy Statement {policy_name} is up to date.")

def send_email(smtp_server, sender_email, receiver_email, message):
    subject = "Routing Policy Update Notification"
    body = message

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

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

    update_policy_statements(router_info, policy_files_directory, filter_name, email_config)

if __name__ == "__main__":
    main()
