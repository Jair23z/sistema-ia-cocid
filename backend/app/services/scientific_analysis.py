"""Shared OpenAI adapter for the scientific-analysis agents.

This module owns provider configuration, the single reusable client and the
mechanics common to every structured Responses API call. Agent prompts remain
in their corresponding role modules.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

from dotenv import load_dotenv
from openai import (
    APIError,
    APITimeoutError,
    AuthenticationError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

AgentRole = Literal["analysis", "synthesis", "comparison"]
StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class AnalysisConfigurationError(Exception):
    """The provider cannot be used because required configuration is absent."""


class AnalysisAuthenticationError(Exception):
    """The provider rejected the configured credentials."""


class AnalysisTimeoutError(Exception):
    """The provider did not respond within the configured timeout."""


class AnalysisRateLimitError(Exception):
    """The provider temporarily rejected the request because of a limit."""


class AnalysisProviderError(Exception):
    """The provider could not complete a structured-output request."""


class AnalysisInvalidResponseError(Exception):
    """The provider response did not satisfy the required schema or evidence."""


@dataclass(frozen=True)
class OpenAIConfiguration:
    api_key: str
    model: str


@dataclass(frozen=True)
class StructuredOutputRun(Generic[StructuredOutput]):
    output: StructuredOutput
    model: str
    input_tokens: int | None
    cached_input_tokens: int | None
    cache_write_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


def get_openai_configuration(role: AgentRole) -> OpenAIConfiguration:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AnalysisConfigurationError("OPENAI_API_KEY is not configured.")

    role_variable = {
        "analysis": "OPENAI_ANALYSIS_MODEL",
        "synthesis": "OPENAI_SYNTHESIS_MODEL",
        "comparison": "OPENAI_COMPARISON_MODEL",
    }[role]
    model = (
        os.getenv(role_variable, "").strip()
        or os.getenv("OPENAI_MODEL", "").strip()
    )
    if not model:
        raise AnalysisConfigurationError(
            f"Neither {role_variable} nor OPENAI_MODEL is configured."
        )

    return OpenAIConfiguration(api_key=api_key, model=model)


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _usage_value(usage: Any, name: str) -> int | None:
    if usage is None:
        return None
    return _optional_non_negative_int(getattr(usage, name, None))


class ScientificAnalysisLLMService:
    """Execute structured agent calls through one lazily created OpenAI client."""

    def __init__(self, timeout_seconds: float = 30.0):
        self._timeout_seconds = timeout_seconds
        self._client: OpenAI | None = None
        self._client_api_key: str | None = None

    def _get_client(self, api_key: str) -> OpenAI:
        if self._client is None or self._client_api_key != api_key:
            self._client = OpenAI(
                api_key=api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
            self._client_api_key = api_key
        return self._client

    def run_structured(
        self,
        *,
        role: AgentRole,
        instructions: str,
        payload: dict[str, Any],
        data_label: str,
        output_schema: type[StructuredOutput],
        max_output_tokens: int,
    ) -> StructuredOutputRun[StructuredOutput]:
        configuration = get_openai_configuration(role)
        client = self._get_client(configuration.api_key)
        serialized_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        provider_input = (
            f"INICIO_{data_label}_NO_CONFIABLE\n"
            f"{serialized_payload}\n"
            f"FIN_{data_label}_NO_CONFIABLE"
        )

        try:
            response = client.responses.parse(
                model=configuration.model,
                instructions=instructions,
                input=provider_input,
                text_format=output_schema,
                max_output_tokens=max_output_tokens,
                store=False,
                tools=[],
            )
        except AuthenticationError as error:
            raise AnalysisAuthenticationError from error
        except APITimeoutError as error:
            raise AnalysisTimeoutError from error
        except RateLimitError as error:
            raise AnalysisRateLimitError from error
        except (
            ContentFilterFinishReasonError,
            LengthFinishReasonError,
        ) as error:
            raise AnalysisInvalidResponseError from error
        except (ValidationError, ValueError, TypeError) as error:
            raise AnalysisInvalidResponseError from error
        except APIError as error:
            raise AnalysisProviderError from error
        except OpenAIError as error:
            raise AnalysisProviderError from error

        try:
            parsed_output = output_schema.model_validate(response.output_parsed)
        except (ValidationError, ValueError, TypeError) as error:
            raise AnalysisInvalidResponseError from error

        usage = getattr(response, "usage", None)
        input_details = getattr(usage, "input_tokens_details", None)
        cached_input_tokens = _optional_non_negative_int(
            getattr(input_details, "cached_tokens", None)
        )
        cache_write_tokens = _optional_non_negative_int(
            getattr(input_details, "cache_write_tokens", None)
        )
        if cache_write_tokens is None:
            cache_write_tokens = _usage_value(usage, "cache_write_tokens")

        return StructuredOutputRun(
            output=parsed_output,
            model=configuration.model,
            input_tokens=_usage_value(usage, "input_tokens"),
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
            output_tokens=_usage_value(usage, "output_tokens"),
            total_tokens=_usage_value(usage, "total_tokens"),
        )
