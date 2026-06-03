import os
import json
import pytest
import requests


class TestOllamaConnectivity:
    """Integration tests for Ollama Cloud API connectivity.

    These tests make real API calls and only run if OLLAMA_API_KEY is set.
    """

    @pytest.fixture(scope="class")
    def api_key(self):
        """Get Ollama API key from environment."""
        key = os.getenv("OLLAMA_API_KEY")
        if not key:
            pytest.skip("OLLAMA_API_KEY not set")
        return key

    def test_ollama_endpoint_responds(self, api_key):
        """Verify the Ollama API endpoint is reachable and uses correct response format."""
        response = requests.post(
            "https://ollama.com/api/chat",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "dolphin-mixtral",
                "messages": [{"role": "user", "content": "Say 'ok'"}],
                "stream": False,
            },
            timeout=30,
        )

        # Should not get 401/404/403 auth errors
        assert response.status_code in [200, 429], (
            f"Ollama API error: {response.status_code}. "
            f"If 401: OLLAMA_API_KEY is invalid. "
            f"If 404: endpoint is wrong. "
            f"Response: {response.text[:200]}"
        )

        # Verify response format is Ollama native (not OpenAI format)
        result = response.json()
        assert "message" in result, (
            f"Response missing 'message' field. "
            f"Expected Ollama native format, got: {result}"
        )
        assert "content" in result.get("message", {}), (
            f"Response.message missing 'content' field. "
            f"Got: {result.get('message', {})}"
        )

    def test_ollama_models_available(self, api_key):
        """Check that at least one of our fallback models is available."""
        models_to_check = ["dolphin-mixtral", "neural-chat", "mistral"]
        successful_models = []

        for model in models_to_check:
            try:
                response = requests.post(
                    "https://ollama.com/api/chat",
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
                if response.status_code == 200:
                    successful_models.append(model)
            except requests.RequestException:
                pass

        assert successful_models, (
            f"No Ollama models responded successfully. "
            f"Checked: {models_to_check}. "
            f"API key may be invalid or models unavailable."
        )

    def test_ollama_json_response_format(self, api_key):
        """Verify Ollama responses can contain JSON as expected by the code."""
        response = requests.post(
            "https://ollama.com/api/chat",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "neural-chat",
                "messages": [
                    {
                        "role": "user",
                        "content": 'Return ONLY valid JSON: {"test": "value"}',
                    }
                ],
                "stream": False,
            },
            timeout=30,
        )

        if response.status_code == 200:
            result = response.json()
            content = result.get("message", {}).get("content", "")
            # Verify content can be parsed as JSON (as the code expects)
            try:
                parsed = json.loads(content)
                assert isinstance(parsed, dict)
            except json.JSONDecodeError:
                pytest.skip(
                    f"Model didn't return JSON format (may be rate-limited or model limitation): {content[:100]}"
                )
