# Copyright (c) 2023 - Lee Hetherington <lee@edgenative.net>
# Script: junos-irrupdater.py

from jnpr.junos import Device
from jnpr.junos.utils.config import Config
import os
import json
import difflib
import sys  # Add sys module for command-line arguments

def read_router_config_for_policy(router_info, policy_name):
    router = None  # Initialize router as None
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
    # Normalize indentation and formatting
    lines = policy_content.strip().split('\n')
    if ignore_first_last_lines and len(lines) > 4:
        lines = lines[2:-2]
    normalized_content = '\n'.join(line.strip() for line in lines)
    return normalized_content

def delete_hierarchy_on_router(router_info, policy_name):
    try:
        router = Device(**router_info)
        router.open()
        with Config(router, mode='exclusive') as cu:
            hierarchy_path = f'policy-options policy-statement {policy_name}'
            cu.load(f'delete {hierarchy_path}', format="set")
            cu.commit()
    except Exception as e:
        print(f"Error deleting hierarchy for {policy_name}: {e}")
    finally:
        if router:
            router.close()

def update_policy_statements(router_info, policy_files_directory, filter_name):
    for filename in os.listdir(policy_files_directory):
        if filename.endswith(".txt") and filename.startswith(filter_name):
            policy_name = filename.split(".")[0]
            print(f"Checking policy {policy_name}...")

            # Read the content of the text file
            with open(os.path.join(policy_files_directory, filename), 'r') as file:
                policy_content = file.read()

            # Normalize policy content from the text file (excluding first and last 2 lines during comparison)
            normalized_policy_content = normalize_policy_content(policy_content, ignore_first_last_lines=True)

            # Read the router's configuration for the specific policy statement
            router_config = read_router_config_for_policy(router_info, policy_name)

            # Check if the hierarchy exists on the router
            if not router_config.strip():
                print(f"Policy hierarchy for {filename} does not exist on the router.")
                print("Inserting policy...")
                try:
                    router = Device(**router_info)
                    router.open()
                    with Config(router) as cu:
                        cu.load(policy_content, format="text")
                        cu.commit()
                    print(f"Inserted policy from {filename}")
                except Exception as e:
                    print(f"Error inserting {filename}: {e}")
                finally:
                    if router:
                        router.close()
            else:
                # Normalize router configuration
                normalized_router_config = normalize_policy_content(router_config)

                # Compare the normalized contents
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
                    # Delete the previous version of the hierarchy on the router
                    delete_hierarchy_on_router(router_info, policy_name)
                    try:
                        router = Device(**router_info)
                        router.open()
                        with Config(router) as cu:
                            cu.load(policy_content, format="text")
                            cu.commit()
                        print(f"Updated policy from {filename}")
                    except Exception as e:
                        print(f"Error updating {filename}: {e}")
                    finally:
                        if router:
                            router.close()
                else:
                    print(f"Policy content for {filename} is up to date.")

def main():
    if len(sys.argv) != 3:
        print("Usage: python junos-irrupdater.py <hostname> <filtername>")
        sys.exit(1)

    hostname = sys.argv[1]
    filter_name = sys.argv[2]
    print(f"Hostname: {hostname}")
    with open("/usr/share/junos-irrupdater/config/routers.conf", "r") as config_file:
        router_info = json.load(config_file)
        router_info["host"] = hostname  # Update the host from command line

    policy_files_directory = "/usr/share/junos-irrupdater/filters"

    update_policy_statements(router_info, policy_files_directory, filter_name)


if __name__ == "__main__":
    main()
