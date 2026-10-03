"""Small synchronous OpenAI-compatible HTTP client; standard library only."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    """Reject redirects before credentials can leave the configured endpoint."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Endpoint redirect rejected", headers, fp)


def urlopen(request, *, timeout):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


class EndpointError(RuntimeError):
    pass


class Client:
    def __init__(self, config: dict):
        self.config = config

    def public_settings(self) -> dict:
        """Record resolved model IDs without serializing keys or arbitrary config fields."""
        return {"roles": {role: {"provider": cfg.get("provider"),
                                "model": os.environ.get(cfg.get("model_env", "")) or cfg.get("model"),
                                "prompt_suffix": cfg.get("prompt_suffix", ""),
                                "response_format": cfg.get("response_format")}
                          for role, cfg in self.config["roles"].items()},
                "decision_reviewer": {k: self.config["decision_reviewer"].get(k) for k in ("provider", "model", "protocol")} if isinstance(self.config.get("decision_reviewer"), dict) else None,
                "verification_mode": self.config["verification_mode"],
                "rewrite_mode": self.config.get("rewrite_mode", "model"),
                "claim_bridge": self.config.get("claim_bridge", False),
                "task_completion": self.config.get("task_completion", "off"),
                "completion_protocol": self.config.get("completion_protocol", "global"),
                "verification_protocol": self.config.get("verification_protocol", "direct"),
                "timeout_seconds": self.config.get("timeout_seconds", 60),
                "max_tokens": self.config.get("max_tokens", 1024)}

    def decide(self, state: dict, questions: dict) -> dict:
        from .jev_client import JevClient
        return JevClient(self.config).decide(state, questions)

    def complete(self, role: str, system: str, payload: dict, *, response_format: dict | None = None) -> str:
        role_cfg = self.config["roles"][role]
        system += "\n" + role_cfg.get("prompt_suffix", "")
        provider = role_cfg["provider"]
        if provider not in ("local", "openrouter"):
            raise ValueError("Provider must be local or openrouter")
        remote = provider == "openrouter"
        base = os.environ.get("OPENROUTER_BASE_URL" if remote else "LM_STUDIO_BASE_URL",
                              "https://openrouter.ai/api/v1" if remote else "http://localhost:1234/v1").rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Invalid endpoint URL")
        if remote and parsed.scheme != "https":
            raise ValueError("OpenRouter requires HTTPS")
        model = os.environ.get(role_cfg.get("model_env", "")) or role_cfg.get("model")
        if not model:
            raise ValueError(f"Set a model for role {role} in config or its model_env")
        key = os.environ.get("OPENROUTER_API_KEY" if remote else "LM_STUDIO_API_KEY", "")
        if remote and not key:
            raise ValueError("OPENROUTER_API_KEY is required for remote roles")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        body = {"model": model, "messages": [{"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                "temperature": 0, "max_tokens": self.config.get("max_tokens", 1024), "stream": False}
        request_format = response_format if response_format is not None else role_cfg.get("response_format")
        if request_format is not None:
            body["response_format"] = request_format
        req = Request(base + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
        try:
            with urlopen(req, timeout=self.config.get("timeout_seconds", 60)) as response:
                data = json.loads(response.read(2_000_000))
        except HTTPError as exc:
            # Do not log remote response bodies or auth headers, which may contain secrets.
            raise EndpointError(f"{role} endpoint returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise EndpointError(f"{role} request failed ({type(exc).__name__})") from None
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise EndpointError(f"{role} response did not finish normally")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip() or len(content) > 12000:
                raise EndpointError(f"{role} returned invalid or oversized text")
            return content.strip()
        except (KeyError, IndexError, TypeError):
            raise EndpointError(f"{role} response has invalid chat-completion shape") from None
