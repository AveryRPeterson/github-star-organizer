# distill.py
import os
import sys
import json
import datetime
import requests
from github_star_organizer.logger import get_logger
from github_star_organizer import state_db


logger = get_logger("distill")


def format_uncategorized_repos(repos):
    """Render pending uncategorized repos in the same markdown format
    previously posted as GitHub issue comments, for the DeepSeek prompt."""
    body = ""
    for r in repos:
        desc = r.get("description") or "No description"
        topics = r.get("topics") or ""
        body += f"- **{r['name_with_owner']}**\n  - Description: {desc}\n  - Topics: {topics}\n\n"
    return body


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
        response = requests.post(url, headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            logger.error(f"DeepSeek API Error: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        logger.error("DeepSeek API call timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to call DeepSeek: {e}")
        return None


def write_outputs(summary, date_suffix=""):
    """Write step outputs for GitHub Actions."""
    if "GITHUB_OUTPUT" not in os.environ:
        return
    has_changes = (
        summary.get("new_keywords_added", 0) > 0 or summary.get("new_categories", 0) > 0
    )
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"date_suffix={date_suffix}\n")
        f.write(f"summary={json.dumps(summary)}\n")
        f.write(f"has_changes={'true' if has_changes else 'false'}\n")


def main():
    try:
        logger.info("Starting distillation...")
        state_db.init_db()

        date_suffix = datetime.date.today().strftime("%Y-W%V")

        pending = state_db.get_uncategorized_repos_full()
        if not pending:
            logger.info("No pending uncategorized repos to distill")
            write_outputs({"status": "skipped", "reason": "no_pending_repos"}, date_suffix=date_suffix)
            return

        logger.info(f"Found {len(pending)} pending uncategorized repos")
        comments = format_uncategorized_repos(pending)

        with open("config.json", "r") as f:
            config = json.load(f)

        prompt = f"""
Analyze the following uncategorized GitHub repositories and suggest updates to the `config.json` provided below.

Current config.json:
{json.dumps(config, indent=2)}

New uncategorized repositories:
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

        logger.info(f"Analyzing {len(pending)} uncategorized repos via DeepSeek...")
        new_config_json = call_deepseek(prompt)

        summary = {
            "status": "success",
            "repos_analyzed": len(pending),
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

                state_db.clear_uncategorized_repos([r["name_with_owner"] for r in pending])
                logger.info(f"Cleared {len(pending)} distilled repos from state DB")

                write_outputs(summary, date_suffix=date_suffix)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse DeepSeek response: {e}")
                summary["status"] = "failed"
                summary["error"] = str(e)
                write_outputs(summary, date_suffix=date_suffix)
        else:
            logger.error("Failed to get response from DeepSeek")
            summary["status"] = "failed"
            summary["error"] = "DeepSeek API failed"
            write_outputs(summary, date_suffix=date_suffix)

    except Exception as e:
        logger.error(f"Distillation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
