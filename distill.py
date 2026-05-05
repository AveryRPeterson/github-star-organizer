# distill.py
import os
import sys
import json
import requests
import subprocess
from github_star_organizer.logger import get_logger
from github_star_organizer.gh_client import GitHubClient, GitHubAPIError


logger = get_logger("distill")


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Command failed: {result.stderr}")
        return None
    return result.stdout.strip()


def get_latest_uncategorized_issue():
    """Find the most recent open uncategorized stars issue"""
    try:
        res = run_command(["gh", "issue", "list", "--state", "open",
                          "--search", "Uncategorized Stars in:title author:@me",
                          "--json", "number,body,title", "--limit", "1"])
        if not res or res == "[]":
            return None
        return json.loads(res)[0]
    except Exception as e:
        logger.error(f"Failed to fetch issue: {e}")
        return None


def get_issue_comments(issue_number):
    """Get comments from an issue (only from owner)"""
    try:
        user = run_command(["gh", "api", "user", "-q", ".login"])
        if not user:
            logger.error("Could not determine current user")
            return ""

        res = run_command(["gh", "issue", "view", str(issue_number),
                          "--json", "comments",
                          "-q", f'.comments[] | select(.author.login == "{user}") | .body'])
        return res if res else ""
    except Exception as e:
        logger.error(f"Failed to get comments: {e}")
        return ""


def call_deepseek(prompt):
    """Call DeepSeek API to analyze uncategorized repos"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.error("DEEPSEEK_API_KEY not found")
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

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            logger.error(f"DeepSeek API Error: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Failed to call DeepSeek: {e}")
        return None


def main():
    try:
        logger.info("Starting distillation...")

        issue = get_latest_uncategorized_issue()
        if not issue:
            logger.info("No open uncategorized issues found")
            return

        issue_number = issue["number"]
        logger.info(f"Found uncategorized issue #{issue_number}")

        comments = get_issue_comments(issue_number)
        if not comments:
            logger.info("No comments found in the issue")
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

        logger.info(f"Analyzing {len(comments)} characters of uncategorized repos via DeepSeek...")
        new_config_json = call_deepseek(prompt)

        summary = {
            "status": "success",
            "repos_analyzed": 0,
            "new_keywords_added": 0,
            "new_categories": 0
        }

        if new_config_json:
            try:
                # Validate JSON
                new_config = json.loads(new_config_json)

                # Calculate diffs
                old_keywords = config.get("keywords", {})
                new_keywords = new_config.get("keywords", {})

                new_cats = [cat for cat in new_keywords if cat not in old_keywords]

                summary["new_keywords_added"] = sum(
                    len(new_keywords[cat]) - len(old_keywords.get(cat, []))
                    for cat in old_keywords if cat in new_keywords
                )
                summary["new_categories"] = len(new_cats)

                with open("config.json", "w") as f:
                    json.dump(new_config, f, indent=2)
                logger.info("config.json has been updated")

                # Extract date from issue title
                issue_title = issue.get("title", "")
                date_suffix = issue_title.split(": ")[-1] if ": " in issue_title else ""

                # Write outputs for GitHub Actions
                if "GITHUB_OUTPUT" in os.environ:
                    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                        f.write(f"date_suffix={date_suffix}\n")
                        f.write(f"issue_num={issue_number}\n")
                        f.write(f"summary={json.dumps(summary)}\n")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse DeepSeek response: {e}")
                summary["status"] = "failed"
                summary["error"] = str(e)
                if "GITHUB_OUTPUT" in os.environ:
                    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                        f.write(f"summary={json.dumps(summary)}\n")
        else:
            logger.error("Failed to get response from DeepSeek")
            summary["status"] = "failed"
            summary["error"] = "DeepSeek API failed"
            if "GITHUB_OUTPUT" in os.environ:
                with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                    f.write(f"summary={json.dumps(summary)}\n")

    except Exception as e:
        logger.error(f"Distillation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
