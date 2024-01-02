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

def read_router_config_for_policy(router_info, policy_name):
    router = None
    try:
        router = Device(**router_info)
        router.open()
        hierarchy_path = f'policy-options policy-statement {policy_name}'
        router_config = router.cli(f'show configuration {hierarchy_path}')
        return router_config.strip()
    except Exception as e:
        print(f"Error reading router configuration: {e}")
    finally:
        if router:
            router.close()

def normalize_policy_content(policy_content, ignore_first_last_lines=False):
    # Normalize the indentation anf formatting, also ignore the first and last 2 lines of the text file
    lines = policy_content.strip().split('\n')
    if ignore_first_last_lines and len(lines) > 4:
        lines = lines[2:-2]
    normalized_content = '\n'.join(line.strip() for line in lines)
    return normalized_content

def delete_hierarchy_on_router(router_info, policy_name):
    # Delete the configuration on the router.  Don't issue a commit, until the policy is re-inserted, otherwise junos complains about referenced policies being deleted.
    try:
        router = Device(**router_info)
        router.open()
        with Config(router, mode='exclusive') as cu:
            hierarchy_path = f'policy-options policy-statement {policy_name}'
            cu.load(f'delete {hierarchy_path}', format="set")
            print(f"Executing: delete {hierarchy_path}")
    except Exception as e:
        print(f"Error deleting hierarchy for {policy_name}: {e}")
    finally:
        if router:
            router.close()

def update_policy_statements(router_info, policy_files_directory, filter_name, email_config):

    # We have the ability to email here, on update of a filter or just on error.  Defined in config/email.conf
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
                print(f"Policy hierarchy for {filename} does not exist on the router.")
                print("Inserting policy...")
                try:
                    router = Device(**router_info)
                    router.open()
                    with Config(router, mode='exclusive') as cu:
                        cu.load(policy_content, format="text")
                        print(f"Inserted policy: {policy_name}")
                        cu.commit(timeout=360)
                    if send_updates:
                        send_email(smtp_server, sender_email, receiver_email, f"Added Routing Policy {policy_name} on {hostname}")

                except Exception as e:
                    print(f"Error inserting {filename}: {e}")
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
                    print("Updating policy...")
                    delete_hierarchy_on_router(router_info, policy_name)
                    try:
                        router = Device(**router_info)
                        router.open()
                        with Config(router, mode='exclusive') as cu:
                            cu.load(policy_content, format="text")
                            print(f"Updated policy: {policy_name}")
                            cu.commit(timeout=360)
                        if send_updates:
                            # Send an email upon update if enabled, that includes the policy_name and hostname of the router
                            send_email(smtp_server, sender_email, receiver_email, f"Updated Routing Policy {policy_name} on {hostname}")

                    except Exception as e:
                        print(f"Error updating {filename}: {e}")
                        if send_errors:
                            # Send an email upon error if enabled, that includes the policy_name and hostname of the router
                            send_email(smtp_server, sender_email, receiver_email, f"Error updating {filename}: {e}")
                    finally:
                        if router:
                            router.close()
                else:
                    print(f"Policy content for {filename} is up to date.")

def tokenize_lines(policy_content):
    # Tidy up the policy content for comparison
    lines = policy_content.strip().split('\n')
    return [line.strip() for line in lines]

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

    with open("/usr/share/junos-irrupdater/config/routers.conf", "r") as config_file:
        router_info = json.load(config_file)
        router_info["host"] = hostname

    with open("/usr/share/junos-irrupdater/config/email.conf", "r") as email_config_file:
        email_config = json.load(email_config_file)

    policy_files_directory = "/usr/share/junos-irrupdater/filters"

    update_policy_statements(router_info, policy_files_directory, filter_name, email_config)

if __name__ == "__main__":
    main()
