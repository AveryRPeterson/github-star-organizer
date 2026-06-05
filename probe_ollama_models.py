"""
Weekly probe script: discover all available Ollama models, seed new ones into
the metrics DB, and reset subscription-gate metrics for models that have
transitioned from paid to free.

Runs via .github/workflows/probe-ollama-models.yml once per week.
"""
import os
import json
import requests
from github_star_organizer.logger import get_logger
from github_star_organizer import state_db

logger = get_logger("probe_ollama_models")

OLLAMA_TAGS_URL = "https://ollama.com/api/tags"
OLLAMA_CHAT_URL = "https://ollama.com/api/chat"
PROBE_TIMEOUT = 30

PROBE_PROMPT = (
    "Respond with the single word: OK"
)


def fetch_available_models(api_key: str) -> list[str]:
    """Fetch all model names from the Ollama /api/tags endpoint."""
    try:
        response = requests.get(
            OLLAMA_TAGS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if response.status_code != 200:
            logger.warning(f"Failed to fetch model list: HTTP {response.status_code}")
            return []
        data = response.json()
        models = [m["name"] for m in data.get("models", [])]
        logger.info(f"Found {len(models)} models on Ollama")
        return models
    except Exception as e:
        logger.error(f"Error fetching model list: {e}")
        return []


def probe_model(api_key: str, model_name: str) -> dict:
    """
    Send a minimal test request to a model. Returns a result dict with keys:
      status_code, success, subscription_required, timeout
    """
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": PROBE_PROMPT}],
        "stream": False,
    }
    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=PROBE_TIMEOUT,
        )
        status = response.status_code
        subscription_required = (
            status == 403
            or (status == 200 and "subscription" in response.text.lower() and "required" in response.text.lower())
        )
        return {
            "status_code": status,
            "success": status == 200 and not subscription_required,
            "subscription_required": subscription_required,
            "timeout": False,
        }
    except requests.Timeout:
        return {"status_code": None, "success": False, "subscription_required": False, "timeout": True}
    except Exception as e:
        logger.warning(f"Error probing {model_name}: {e}")
        return {"status_code": None, "success": False, "subscription_required": False, "timeout": False}


def main() -> None:
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        logger.error("OLLAMA_API_KEY not set — cannot probe models")
        return

    state_db.init_db()

    available_models = fetch_available_models(api_key)
    if not available_models:
        logger.warning("No models returned from /api/tags — aborting probe")
        return

    known_models = set(state_db.get_all_known_ollama_models())
    new_models = [m for m in available_models if m not in known_models]
    logger.info(f"New models to probe: {len(new_models)} ({new_models})")

    transitioned_to_free = []
    already_gated = []

    for model_name in available_models:
        result = probe_model(api_key, model_name)
        logger.info(
            f"Probed {model_name}: status={result['status_code']} "
            f"success={result['success']} "
            f"subscription_required={result['subscription_required']} "
            f"timeout={result['timeout']}"
        )

        state_db.record_ollama_model_metric(
            model_name=model_name,
            success=result["success"],
            status_code=result["status_code"] if not result["success"] else None,
            timeout=result["timeout"],
        )

        # Detect free-tier transition: had prior 403 history but now succeeds
        if result["success"] and model_name in known_models:
            prior_metrics = _get_model_metrics(model_name)
            if prior_metrics and prior_metrics.get("subscription_403_count", 0) > 0:
                logger.info(
                    f"Free-tier transition detected for {model_name} "
                    f"(had {prior_metrics['subscription_403_count']} prior 403s) — resetting subscription metrics"
                )
                state_db.reset_subscription_metrics(model_name)
                transitioned_to_free.append(model_name)
        elif result["subscription_required"]:
            already_gated.append(model_name)

    logger.info(
        f"Probe complete. "
        f"New models seeded: {len(new_models)}, "
        f"Free-tier transitions: {len(transitioned_to_free)} {transitioned_to_free}, "
        f"Subscription-gated: {len(already_gated)}"
    )

    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"models_probed={len(available_models)}\n")
            f.write(f"new_models={len(new_models)}\n")
            f.write(f"transitioned_to_free={len(transitioned_to_free)}\n")
            f.write(f"subscription_gated={len(already_gated)}\n")


def _get_model_metrics(model_name: str) -> dict | None:
    """Fetch current metrics row for a model from the DB."""
    import sqlite3
    db_path = state_db.DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM ollama_model_metrics WHERE model_name = ?",
            (model_name,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


if __name__ == "__main__":
    main()
