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
        """Verify OLLAMA_API_KEY authenticates successfully (no 401/403 on key level)."""
        response = requests.get(
            f"{OLLAMA_API_BASE}/api/tags",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        assert response.status_code != 401, (
            "OLLAMA_API_KEY is invalid or expired (got 401)"
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

    def test_at_least_one_model_accessible(self, api_key, available_models):
        """Verify at least one model is accessible (not all require paid subscription)."""
        if not available_models:
            pytest.skip("Could not fetch available models list")

        accessible_models = []
        for model in available_models[:5]:  # Test first 5 to avoid rate limits
            try:
                response = requests.post(
                    f"{OLLAMA_API_BASE}/api/chat",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "test"}],
                        "stream": False,
                    },
                    timeout=10,
                )
                # 403 = subscription required (skip), 200 = works, others = various errors
                if response.status_code == 200:
                    accessible_models.append(model)
                elif response.status_code == 403:
                    pass  # Model requires subscription, skip
                elif response.status_code == 429:
                    pass  # Rate limited, skip
                # Other errors still count as attempt
            except requests.RequestException:
                pass

        assert accessible_models, (
            f"No free models are accessible. All tested models either require subscription or failed. "
            f"Models available: {available_models}\n"
            f"Free plan limitations on Ollama Cloud may require upgrading. "
            f"See: https://ollama.com/upgrade"
        )

    def test_dynamic_model_discovery_doesnt_crash(self, api_key):
        """Verify the dynamic model discovery function works as expected."""
        # This mimics what get_available_ollama_models() does
        try:
            response = requests.get(
                f"{OLLAMA_API_BASE}/api/tags",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            assert response.status_code == 200, f"Failed to fetch models: {response.status_code}"

            data = response.json()
            all_models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            assert all_models, "No models in response"

            # Filter out non-chat models
            excluded_keywords = {"vision", "audio", "video", "image", "embed"}
            chat_models = [
                m for m in all_models
                if not any(kw in m.lower() for kw in excluded_keywords)
            ]

            # Should have at least some chat models
            assert chat_models, (
                f"No chat models found after filtering. All models: {all_models}"
            )

        except requests.RequestException as e:
            pytest.fail(f"Dynamic discovery failed: {e}")
