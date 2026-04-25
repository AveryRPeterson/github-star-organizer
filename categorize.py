import subprocess
import json
import sys

# Your List IDs
LISTS = {
    "AI Agents & LLMs": "UL_kwDOAHb0k84AeBvM",
    "Tools & CLI": "UL_kwDOAHb0k84AeBvN",
    "Hardware & Keyboards": "UL_kwDOAHb0k84AeBvO",
    "Android & Termux": "UL_kwDOAHb0k84AeBvP",
    "3D Printing & CAD": "UL_kwDOAHb0k84AeBvT",
    "OS & Customization": "UL_kwDOAHb0k84AeBxQ",
    "Dev Tools & Frameworks": "UL_kwDOAHb0k84AeBxR"
}

KEYWORDS = {
    "AI Agents & LLMs": ["ai", "llm", "agent", "autonomous", "gpt", "claude", "inference", "machine-learning", "deep-learning", "anthropic", "openai", "mcp", "skills", "agentic", "transformers", "pytorch", "tensorflow", "rag", "embeddings", "ollama", "vllm", "diffusion", "chatbot"],
    "Tools & CLI": ["cli", "terminal", "shell", "fish", "prompt", "tui", "utility", "tool", "plugin", "manager", "zsh", "bash", "tmux", "git", "vim", "neovim", "editor", "config", "dotfiles", "starship", "fisher"],
    "Hardware & Keyboards": ["keyboard", "hardware", "ergonomic", "split-keyboard", "mechanical-keyboard", "qmk", "zmk", "firmware", "pcb", "kicad", "keycap"],
    "Android & Termux": ["android", "termux", "apk", "root", "adb", "magisk", "xposed", "lineageos", "recovery", "bootloader", "shizuku"],
    "3D Printing & CAD": ["3d", "cad", "scad", "printing", "printer", "mesh", "splat", "gaussian", "stl", "marlin", "voron", "klipper", "cura", "prusaslicer", "blender", "modeling", "cnc", "openscad"],
    "OS & Customization": ["linux", "kernel", "boot", "grub", "ventoy", "theme", "catppuccin", "dracula", "nord", "wallpaper", "desktop", "font", "nerd-font", "icon", "styling", "customization"],
    "Dev Tools & Frameworks": ["framework", "javascript", "typescript", "python", "rust", "go", "nodejs", "react", "vue", "svelte", "docker", "kubernetes", "aws", "firebase", "api", "backend", "frontend", "web", "compiler", "runtime", "bun", "yarn", "npm"]
}

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
    if any(kw in combined for kw in KEYWORDS["AI Agents & LLMs"]):
        return "AI Agents & LLMs"
    if any(kw in combined for kw in KEYWORDS["3D Printing & CAD"]):
        return "3D Printing & CAD"
    if any(kw in combined for kw in KEYWORDS["Android & Termux"]):
        return "Android & Termux"
    if any(kw in combined for kw in KEYWORDS["Hardware & Keyboards"]):
        return "Hardware & Keyboards"
    if any(kw in combined for kw in KEYWORDS["Tools & CLI"]):
        return "Tools & CLI"
    if any(kw in combined for kw in KEYWORDS["OS & Customization"]):
        return "OS & Customization"
    if any(kw in combined for kw in KEYWORDS["Dev Tools & Frameworks"]):
        return "Dev Tools & Frameworks"
    return None

def main():
    print("Fetching already categorized stars...")
    categorized = get_categorized_ids()
    print(f"Found {len(categorized)} categorized repositories.")
    
    print("Fetching recent stars...")
    stars = get_recent_stars()
    
    if not stars or "data" not in stars:
        print("Failed to fetch stars.")
        return

    for repo in stars["data"]["viewer"]["starredRepositories"]["nodes"]:
        if repo["id"] not in categorized:
            cat = categorize(repo)
            if cat:
                print(f"Categorizing {repo['nameWithOwner']} into {cat}...")
                run_query("""
                mutation($repoId: ID!, $listId: ID!) {
                  updateUserListsForItem(input: {itemId: $repoId, listIds: [$listId]}) { clientMutationId }
                }
                """, {"repoId": repo["id"], "listId": LISTS[cat]})
            else:
                print(f"Skipping {repo['nameWithOwner']} (no keyword match).")
        else:
            print(f"Skipping {repo['nameWithOwner']} (already categorized).")

if __name__ == "__main__":
    main()
