#!/usr/bin/env python3
import os
import subprocess
import sys
import time

import jwt
import requests

pem_path = "..."
client_id = "..."

prompt = """
Use gh to list the available repositories. Create an issue in them called 'Testing Claude Agent',
then clone the repo, introduce a dummy change in the README, create a branch, push the change and
open a PR that solves the issue.
"""

with open(pem_path, "rb") as pem_file:
    signing_key = pem_file.read()

payload = {
    "iat": int(time.time()),
    "exp": int(time.time()) + 600,  # 10 minute expiration
    "iss": client_id,
}

encoded_jwt = jwt.encode(payload, signing_key, algorithm="RS256")

response = requests.get(
    "https://api.github.com/app/installations",
    headers={
        "Authorization": f"Bearer {encoded_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    },
    timeout=60,
)

if response.status_code != 200:
    print(f"Error fetching installations: {response.status_code} {response.text}", file=sys.stderr)
    sys.exit(1)

installations = response.json()
print(f"Found {len(installations)} installation(s):\n")

gh_headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

for inst in installations:
    installation_id = inst["id"]
    account = inst.get("account", {})
    print(f"Installation ID: {installation_id}")
    print(f"  Account:     {account.get('login', 'N/A')} ({account.get('type', 'N/A')})")
    print(f"  Target type: {inst.get('target_type', 'N/A')}")

    # Create an installation access token
    token_resp = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={**gh_headers, "Authorization": f"Bearer {encoded_jwt}"},
        timeout=60,
    )
    if token_resp.status_code != 201:
        print(f"  ERROR creating token: {token_resp.status_code} {token_resp.text}")
        print()
        continue

    token_data = token_resp.json()
    install_token = token_data["token"]
    print(f"  Token:       {install_token[:12]}... (expires {token_data.get('expires_at', 'N/A')})")

    # List repositories accessible to this installation token
    repos_resp = requests.get(
        "https://api.github.com/installation/repositories",
        headers={**gh_headers, "Authorization": f"Bearer {install_token}"},
        timeout=60,
    )
    if repos_resp.status_code != 200:
        print(f"  ERROR listing repos: {repos_resp.status_code} {repos_resp.text}")
        print()
        continue

    repos = repos_resp.json().get("repositories", [])
    print(f"  Repositories ({len(repos)}):")
    for repo in repos:
        # Create a repo-scoped token (limited to just this repository)
        repo_token_resp = requests.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={**gh_headers, "Authorization": f"Bearer {encoded_jwt}"},
            json={"repository_ids": [repo["id"]]},
            timeout=60,
        )
        if repo_token_resp.status_code == 201:
            repo_token_data = repo_token_resp.json()
            repo_token = repo_token_data["token"]
            expires_at = repo_token_data.get("expires_at", "N/A")
            print(f"    - {repo['full_name']} (id: {repo['id']})")
            print(f"      Scoped token: {repo_token[:12]}... (expires {expires_at})")

            # Launch a Claude agent with the repo-scoped GH_TOKEN
            print(f"      Launching Claude agent for {repo['full_name']}...")
            agent_env = {**os.environ, "GH_TOKEN": repo_token}
            result = subprocess.run(
                [
                    "claude",  # nosec
                    "--print",
                    "--dangerously-skip-permissions",
                    prompt,
                ],
                env=agent_env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            print("      Agent output:")
            for line in result.stdout.strip().splitlines():
                print(f"        {line}")
            if result.returncode != 0 and result.stderr:
                print("      Agent stderr:")
                for line in result.stderr.strip().splitlines():
                    print(f"        {line}")
        else:
            status_code = repo_token_resp.status_code
            text = repo_token_resp.text
            print(f"    - {repo['full_name']} (id: {repo['id']})")
            print(f"      ERROR creating scoped token: {status_code} {text}")
    print()
