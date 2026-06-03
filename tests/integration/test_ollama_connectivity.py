import os
import json
import pytest
import requests


OLLAMA_API_BASE = "https://ollama.com"


class TestOllamaConnectivity:
    """Integration tests for Ollama Cloud API connectivity.

    These tests make real API calls and only run if OLLAMA_API_KEY is set.
    """

    @pytest.fixture(scope="class")
    def api_key(self):
        key = os.getenv("OLLAMA_API_KEY")
        if not key:
            pytest.skip("OLLAMA_API_KEY not set")
        return key

    @pytest.fixture(scope="class")
    def available_models(self, api_key):
        """Fetch available models from the Ollama Cloud API."""
        try:
            response = requests.get(
                f"{OLLAMA_API_BASE}/api/tags",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except requests.RequestException:
            pass
        return []

    def test_api_key_is_valid(self, api_key):
        """Verify OLLAMA_API_KEY authenticates successfully (no 401/403)."""
        response = requests.get(
            f"{OLLAMA_API_BASE}/api/tags",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        assert response.status_code != 401, (
            "OLLAMA_API_KEY is invalid or expired (got 401)"
        )
        assert response.status_code != 403, (
            "OLLAMA_API_KEY is forbidden (got 403)"
        )
        assert response.status_code == 200, (
            f"Unexpected status from Ollama API: {response.status_code} — {response.text[:200]}"
        )

    def test_available_models_listed(self, api_key, available_models):
        """Verify we can list models and at least one is available."""
        assert available_models, (
            "No models returned from https://ollama.com/api/tags. "
            "The Ollama Cloud API may not have any models available for this key."
        )

    def test_configured_models_available(self, api_key, available_models):
        """Check that the models configured in discover_repos.py are available."""
        if not available_models:
            pytest.skip("Could not fetch available models list")

        configured_models = ["dolphin-mixtral", "neural-chat", "mistral"]
        missing = [m for m in configured_models if not any(
            m in avail for avail in available_models
        )]

        if missing:
            pytest.fail(
                f"Models configured in discover_repos.py not found in Ollama Cloud: {missing}\n"
                f"Available models: {available_models}\n"
                f"Update the ollama_models list in _identify_via_ollama() and call_ollama_summaries() "
                f"to use available models."
            )

    def test_chat_endpoint_responds(self, api_key, available_models):
        """Verify the chat endpoint works with an available model."""
        if not available_models:
            pytest.skip("No available models to test with")

        test_model = available_models[0]
        response = requests.post(
            f"{OLLAMA_API_BASE}/api/chat",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": test_model,
                "messages": [{"role": "user", "content": "Say 'ok'"}],
                "stream": False,
            },
            timeout=30,
        )

        assert response.status_code in [200, 429], (
            f"Chat endpoint error with model '{test_model}': {response.status_code} — {response.text[:200]}"
        )

        if response.status_code == 200:
            result = response.json()
            # Verify Ollama native response format (not OpenAI format)
            assert "message" in result, (
                f"Response missing 'message' key. "
                f"Expected Ollama native format, got: {list(result.keys())}"
            )
            assert "content" in result.get("message", {}), (
                f"Response.message missing 'content'. Got: {result.get('message', {})}"
            )
