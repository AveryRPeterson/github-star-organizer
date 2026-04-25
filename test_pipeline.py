import subprocess
import time
import sys
import json

TEST_REPOS = [
    "pieeg-club/ironbci",
    "ntpz870817/Chamaeleo",
    "MindQuantum-HiQ/HiQsimulator",
    "Deltaphish/UwUpp",
    "PlasmaPy/PlasmaPy"
]

def run_command(cmd, capture=True):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0 and capture:
        print(f"Error: {result.stderr}", file=sys.stderr)
    return result

def star_repo(repo):
    print(f"Starring {repo}...")
    run_command(["gh", "api", "-X", "PUT", f"/user/starred/{repo}"])

def trigger_workflow(workflow_name):
    print(f"Triggering {workflow_name} workflow...")
    run_command(["gh", "workflow", "run", workflow_name])

def get_latest_run_id(workflow_name):
    # Wait a few seconds for the run to register
    time.sleep(5)
    res = run_command(["gh", "run", "list", "--workflow", workflow_name, "--json", "databaseId,status", "--limit", "1"])
    if res and res.stdout:
        data = json.loads(res.stdout.strip())
        if data:
            return data[0]["databaseId"]
    return None

def wait_for_run(run_id):
    print(f"Waiting for run {run_id} to complete...")
    run_command(["gh", "run", "watch", str(run_id)], capture=False)

def main():
    print("--- 1. Starring Test Repositories ---")
    for repo in TEST_REPOS:
        star_repo(repo)
    
    print("\n--- 2. Triggering Organization Runner ---")
    trigger_workflow("organize.yml")
    
    org_run_id = get_latest_run_id("organize.yml")
    if org_run_id:
        wait_for_run(org_run_id)
    else:
        print("Could not find the organization run ID. Waiting 30 seconds...")
        time.sleep(30)
    
    print("\n--- 3. Triggering Distillation Runner ---")
    trigger_workflow("distill.yml")
    
    dist_run_id = get_latest_run_id("distill.yml")
    if dist_run_id:
        wait_for_run(dist_run_id)
    else:
        print("Could not find the distillation run ID. It may take a moment to start.")
        
    print("\nPipeline test complete. Check the 'Pull requests' tab for the new categories!")

if __name__ == "__main__":
    main()
