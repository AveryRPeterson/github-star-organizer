import os
import subprocess
import json
import sys
import requests

def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        return None
    return result.stdout.strip()

def get_latest_uncategorized_issue():
    # Find the most recent open issue for uncategorized stars from the owner
    # author:@me is a gh CLI alias for the current authenticated user
    res = run_command(["gh", "issue", "list", "--state", "open", "--search", "Uncategorized Stars in:title author:@me", "--json", "number,body,title", "--limit", "1"])
    if not res or res == "[]":
        return None
    return json.loads(res)[0]

def get_issue_comments(issue_number):
    # Only pull comments from the owner to prevent hijacking
    user = run_command(["gh", "api", "user", "--json", "login", "-q", ".login"])
    if not user:
        print("Error: Could not determine current user.", file=sys.stderr)
        return ""

    res = run_command(["gh", "issue", "view", str(issue_number), "--json", "comments", "-q", f'.comments[] | select(.author.login == "{user}") | .body'])
    return res if res else ""

def call_deepseek(prompt):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY not found")
        return None
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a specialized data organizer for GitHub stars. Your goal is to analyze uncategorized repositories and update a JSON configuration containing category-to-keyword mappings. Always return valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        print(f"DeepSeek API Error: {response.status_code} - {response.text}")
        return None

def main():
    issue = get_latest_uncategorized_issue()
    if not issue:
        print("No open uncategorized issues found.")
        return

    issue_number = issue["number"]
    comments = get_issue_comments(issue_number)
    
    if not comments:
        print("No comments found in the issue.")
        return

    with open("config.json", "r") as f:
        config = json.load(f)

    prompt = f"""
Analyze the following uncategorized GitHub repositories and suggest updates to the `config.json` provided below.

Current config.json:
{json.dumps(config, indent=2)}

New uncategorized repositories (from issue comments):
{comments}

Instructions:
1. Identify common themes among the uncategorized repositories.
2. If a repository fits an existing category, suggest adding new specific keywords to that category in `config.json` to capture it in the future.
3. If several repositories form a clear new theme (e.g., 'Cybersecurity', 'Game Dev', 'Self-Hosted'), suggest a new category name and a list of keywords. 
4. DO NOT suggest a list ID for new categories (leave it empty or omit if you can't create one).
5. Ensure the resulting JSON matches the structure of `config.json`.
6. Be surgical: add precise keywords that won't cause false positives.

Return ONLY the complete updated `config.json` object.
"""

    print(f"Analyzing uncategorized repos from issue #{issue_number} via DeepSeek...")
    new_config_json = call_deepseek(prompt)
    
    if new_config_json:
        try:
            # Validate JSON
            new_config = json.loads(new_config_json)
            with open("config.json", "w") as f:
                json.dump(new_config, f, indent=2)
            print("config.json has been updated locally.")
            
            # Extract date from issue title for the PR title
            # Title format: "Uncategorized Stars: 2026-W16"
            issue_title = issue.get("title", "")
            date_suffix = issue_title.split(": ")[-1] if ": " in issue_title else ""
            
            if "GITHUB_OUTPUT" in os.environ:
                with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                    f.write(f"date_suffix={date_suffix}\n")
                    f.write(f"issue_num={issue_number}\n")
                    
        except Exception as e:
            print(f"Failed to parse DeepSeek response as JSON: {e}")
            print(new_config_json)
    else:
        print("Failed to get response from DeepSeek.")

if __name__ == "__main__":
    main()
