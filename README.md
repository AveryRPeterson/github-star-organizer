# GitHub Star Organizer

A GitHub Actions workflow system that automatically discovers, categorizes, and summarizes interesting repositories to help organize and expand your GitHub stars.

## Features

- **Discover Interesting Repos**: Dual-model AI analysis (DeepSeek + Ollama) identifies 13 unique repositories per week that are unusual, innovative, or solve problems in creative ways
- **Keyword-Based Categorization**: Automatically categorizes repositories by topic using configurable keywords
- **Weekly Organization**: Creates GitHub issues for:
  - Uncategorized popular repositories (for keyword growth)
  - Interesting discoveries with AI-generated summaries
- **Smart Deduplication**: Removes already-starred repos and previously flagged discoveries to prevent redundant suggestions

## Workflows

### discover-repos.yml
Runs weekly (Saturdays 11pm UTC) to discover new interesting repositories:
1. Fetches popular repos from GitHub (created after 2023, 1000+ stars)
2. Splits into uncategorized (Stage 1) and categorized (Stage 2+3)
3. Reports new uncategorized repos for keyword expansion
4. Uses DeepSeek and Ollama to identify 13 interesting repos per run
5. Creates GitHub issues with AI-generated summaries

**Output**: ~13 new interesting repositories + uncategorized repos for keyword growth each week

### organize.yml
Automatically stars/unstarred repos based on discovery issue state

### distill.py
Consolidates weekly discoveries into permanent category files

## Configuration

Edit `config.json` to customize:
- Category keywords for auto-categorization
- Exclusion patterns
- Repository search criteria

## API Requirements

The workflows require:
- `DEEPSEEK_API_KEY`: DeepSeek API access
- `OLLAMA_CLOUD_KEY`: Ollama Cloud access
- GitHub token with `issues:write` and `contents:read` permissions

## Testing

Run unit tests:
```bash
python -m pytest tests/unit/ -v
```

## Project Structure

```
.
├── .github/workflows/      # GitHub Actions workflows
├── github_star_organizer/  # Main package
│   ├── categorizer.py      # Category matching logic
│   ├── gh_client.py        # GitHub GraphQL client
│   └── issue_manager.py    # Issue creation/parsing
├── discover_repos.py       # Main discovery workflow
├── distill.py              # Category consolidation
├── config.json             # Configuration
└── tests/                  # Unit tests
```

## How It Works

1. **Search**: Fetches up to 100 popular repos from GitHub
2. **Split**: Separates into categorized and uncategorized repos
3. **Dedup**: Removes user's starred repos and already-flagged discoveries
4. **Identify**: DeepSeek analyzes first half (identifies 7), Ollama analyzes second half (identifies 6)
5. **Summarize**: Both models generate detailed summaries for the 13 selected repos
6. **Report**: Posts results to GitHub issues for weekly review

## Development

Changes to the discover-repos workflow are developed on feature branches and require PR review before merging to main.
