import subprocess
import json
import sys
import datetime
import os
import re

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

config = load_config()
LISTS = config["lists"]
KEYWORDS = config["keywords"]

PRIORITY_CATEGORIES = [
    "AI Agents & LLMs",
    "3D Printing & CAD",
    "OS & Customization",
    "Android & Termux",
    "Hardware & Keyboards",
    "Tools & CLI",
    "Dev Tools & Frameworks"
]

def run_query(query, variables=None):
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if variables:
        for k, v in variables.items():
            cmd.extend(["-f", f"{k}={v}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        return None
    return json.loads(result.stdout)

def get_categorized_ids():
    query = """
    query {
      viewer {
        lists(first: 100) {
          nodes {
            items(first: 100) {
              nodes {
                ... on Repository { id }
              }
            }
          }
        }
      }
    }
    """
    data = run_query(query)
    ids = set()
    if data and "data" in data:
        for list_node in data["data"]["viewer"]["lists"]["nodes"]:
            for item in list_node["items"]["nodes"]:
                if item and "id" in item:
                    ids.add(item["id"])
    return ids

def get_recent_stars():
    query = """
    query {
      viewer {
        starredRepositories(first: 50, orderBy: {field: STARRED_AT, direction: DESC}) {
          nodes {
            id
            nameWithOwner
            description
            repositoryTopics(first: 10) {
              nodes { topic { name } }
            }
          }
        }
      }
    }
    """
    return run_query(query)

def categorize(repo):
    name = repo.get("nameWithOwner", "").lower()
    desc = (repo.get("description") or "").lower()
    topics = [t["topic"]["name"].lower() for t in repo.get("repositoryTopics", {}).get("nodes", [])]
    combined = f"{name} {desc} {' '.join(topics)}"
    
    # Priority matching
    for cat in PRIORITY_CATEGORIES:
        if any(kw in combined for kw in KEYWORDS.get(cat, [])):
            return cat
        
    # Check any dynamic categories added to config.json
    for cat, kws in KEYWORDS.items():
        if cat not in PRIORITY_CATEGORIES:
            if any(kw in combined for kw in kws):
                return cat
                
    return None

def get_or_create_issue():
    # Group issues by year and week to create a rolling "Weekly" issue
    date_str = datetime.date.today().strftime("%Y-W%V")
    target_title = f"Uncategorized Stars: {date_str}"
    
    # 1. Find all open uncategorized issues authored by me
    res = subprocess.run(["gh", "issue", "list", "--state", "open", "--search", 'in:title "Uncategorized Stars" author:@me', "--json", "number,title"], capture_output=True, text=True)
    
    open_issues = []
    if res.returncode == 0 and res.stdout.strip():
        try:
            open_issues = json.loads(res.stdout.strip())
        except json.JSONDecodeError:
            pass

    target_issue_num = None
    old_issues = []

    for issue in open_issues:
        if issue["title"] == target_title:
            if not target_issue_num:
                target_issue_num = str(issue["number"])
            else:
                # If we already have a target but found another one with the same title,
                # treat the subsequent ones as duplicates to be closed.
                old_issues.append(str(issue["number"]))
        else:
            old_issues.append(str(issue["number"]))

    # 2. If target issue doesn't exist, create it
    if not target_issue_num:
        body = "This issue tracks repositories that were skipped during the organization run because they did not match any existing keywords. Comments below contain batches of uncategorized repositories."
        res_create = subprocess.run(["gh", "issue", "create", "--title", target_title, "--body", body], capture_output=True, text=True)
        if res_create.returncode == 0:
            url = res_create.stdout.strip()
            target_issue_num = url.split("/")[-1]
        else:
            print(f"Failed to create issue: {res_create.stderr}")
            return None

    # 3. Close old issues, pointing them to the new target issue
    for old_issue_num in old_issues:
        comment = f"A new weekly issue has been created: #{target_issue_num}. Closing this older tracking issue."
        subprocess.run(["gh", "issue", "comment", old_issue_num, "--body", comment])
        subprocess.run(["gh", "issue", "close", old_issue_num, "--reason", "not planned"])
        print(f"Closed old tracking issue #{old_issue_num}")

    return target_issue_num

def get_already_reported_repos(issue_number):
    if not issue_number:
        return set()
    
    # Fetch all comments' bodies from the issue
    res = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "comments", "-q", ".comments[].body"],
        capture_output=True, text=True
    )
    if res.returncode != 0:
        print(f"Failed to fetch comments for issue #{issue_number}: {res.stderr}")
        return set()
    
    # Extract nameWithOwner using regex from the markdown list items
    reported = set()
    # Looking for lines like "- **user/repo**"
    matches = re.findall(r"- \*\*([^*]+)\*\*", res.stdout)
    for match in matches:
        reported.add(match)
        
    return reported

def report_uncategorized(issue_number, skipped_repos):
    if not skipped_repos or not issue_number:
        return
    comment_body = "### New Uncategorized Repositories\n\n"
    for r in skipped_repos:
        topics = ", ".join([t["topic"]["name"] for t in r.get("repositoryTopics", {}).get("nodes", [])])
        desc = r.get('description') or "No description"
        comment_body += f"- **{r['nameWithOwner']}**\n  - Description: {desc}\n  - Topics: {topics}\n\n"
        
    res = subprocess.run(["gh", "issue", "comment", str(issue_number), "--body", comment_body])
    if res.returncode != 0:
        print(f"Failed to post comment: {res.stderr}")

def main():
    print("Fetching already categorized stars...")
    categorized = get_categorized_ids()
    print(f"Found {len(categorized)} categorized repositories.")
    
    print("Fetching recent stars...")
    stars = get_recent_stars()
    
    if not stars or "data" not in stars:
        print("Failed to fetch stars.")
        return

    skipped_repos = []

    for repo in stars["data"]["viewer"]["starredRepositories"]["nodes"]:
        if repo["id"] not in categorized:
            cat = categorize(repo)
            if cat:
                print(f"Categorizing {repo['nameWithOwner']} into {cat}...")
                run_query("""
                mutation($repoId: ID!, $listId: ID!) {
                  updateUserListsForItem(input: {itemId: $repoId, listIds: [$listId]}) { clientMutationId }
                }
                """, {"repoId": repo["id"], "listId": LISTS.get(cat)})
            else:
                print(f"Skipping {repo['nameWithOwner']} (no keyword match).")
                skipped_repos.append(repo)
        else:
            print(f"Skipping {repo['nameWithOwner']} (already categorized).")
            
    if skipped_repos:
        print(f"Preparing to report {len(skipped_repos)} uncategorized repos...")
        issue_num = get_or_create_issue()
        if issue_num:
            already_reported = get_already_reported_repos(issue_num)
            
            new_to_report = [repo for repo in skipped_repos if repo['nameWithOwner'] not in already_reported]
            
            if new_to_report:
                print(f"Reporting {len(new_to_report)} new uncategorized repos to issue #{issue_num}...")
                report_uncategorized(issue_num, new_to_report)
                print(f"Comment added to issue #{issue_num}.")
            else:
                print("All skipped repos have already been reported.")

if __name__ == "__main__":
    main()
