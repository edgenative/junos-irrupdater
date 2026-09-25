# Copyright (c) 2023-2026 - Lee Hetherington <lee@edgenative.net>
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

# ---------------------------------------------------------------------------
# Local safety checks - run BEFORE anything is pushed to the router.
#
# Background: a full disk once left every db/*.agg file at 0 bytes. The filter
# generator turned those into policies containing only a reject term, this
# script saw they "differed" from the router, and pushed them. Every prefix was
# then rejected in and out on every router. These checks make that impossible:
#
#   1. an empty or structurally broken policy file is never pushed
#   2. a copy of every policy is kept in filters/last-pushed/ after a successful
#      push (and seeded when a policy is found to be up to date)
#   3. before pushing, the new file is compared with that copy - if it lost all
#      of its route-filter/prefix-list entries, or more than SHRINK_REFUSE_RATIO
#      of them (once the baseline had at least SHRINK_MIN_BASELINE entries),
#      the push is refused and an error is reported
#
# A known-good large change can be pushed by setting IRRUPDATER_FORCE=1 in the
# environment; that bypasses check 3 only. Checks 1 and 2 always apply.
# ---------------------------------------------------------------------------
LAST_PUSHED_DIR = f"{path}/filters/last-pushed"
SHRINK_MIN_BASELINE = 10   # apply the ratio check only when the last pushed copy had at least this many entries
SHRINK_REFUSE_RATIO = 0.8  # refuse when more than 80% of the entries disappeared
PREFIX_ENTRY_KEYWORDS = ("route-filter ", "prefix-list ", "prefix-list-filter ", "source-address-filter ")

def count_prefix_entries(policy_content):
    # Number of lines in the policy that match on a prefix.
    return sum(1 for line in policy_content.splitlines() if line.strip().startswith(PREFIX_ENTRY_KEYWORDS))

def last_pushed_file(policy_name):
    return os.path.join(LAST_PUSHED_DIR, f"{policy_name}.txt")

def sanity_check_policy(policy_name, policy_content):
    # Returns None when the policy is safe to push, otherwise a string saying why it must not be.
    if not policy_content.strip():
        return "policy file is empty"
    if f"policy-statement {policy_name}" not in policy_content:
        return f"policy file does not define policy-statement {policy_name}"
    if policy_content.count("{") != policy_content.count("}"):
        return "policy file has unbalanced braces (truncated write?)"

    baseline = last_pushed_file(policy_name)
    if not os.path.isfile(baseline):
        return None

    with open(baseline, "r") as f:
        old_count = count_prefix_entries(f.read())
    new_count = count_prefix_entries(policy_content)
    force = os.environ.get("IRRUPDATER_FORCE") == "1"

    if old_count > 0 and new_count == 0:
        reason = f"policy lost all {old_count} prefix entries since the last push"
    elif old_count >= SHRINK_MIN_BASELINE and new_count < old_count * (1 - SHRINK_REFUSE_RATIO):
        reason = f"prefix entries dropped from {old_count} to {new_count} (more than {int(SHRINK_REFUSE_RATIO * 100)}% shrink)"
    else:
        return None

    if force:
        print(f"WARNING: {reason} - pushing anyway because IRRUPDATER_FORCE=1")
        return None
    return f"{reason}; refusing to push. Set IRRUPDATER_FORCE=1 to override if this is expected"

def record_last_pushed(policy_name, policy_content):
    # Remember what the router now has, so the next run has something to compare against.
    try:
        os.makedirs(LAST_PUSHED_DIR, exist_ok=True)
        tmp = last_pushed_file(policy_name) + ".tmp"
        with open(tmp, "w") as f:
            f.write(policy_content)
        os.replace(tmp, last_pushed_file(policy_name))
    except OSError as e:
        print(f"WARNING: could not record last pushed copy of {policy_name}: {e}")

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

        problem = sanity_check_policy(policy_name, policy_content)
        if problem:
            print(f"REFUSED: {policy_name} on {hostname}: {problem}")
            if send_errors:
                send_email(smtp_server, sender_email, receiver_email,
                           f"REFUSED to push routing policy {policy_name} on {hostname}: {problem}")
            continue

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
                record_last_pushed(policy_name, policy_content)
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
            record_last_pushed(policy_name, policy_content)
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
