from __future__ import annotations

import logging
from pathlib import Path

from intent_router_harness.config import AppSettings
from intent_router_harness.llm import (
    LLMConfigurationError,
    OpenAICompatibleLLMClient,
    load_llm_settings,
)
from intent_router_harness.service import IntentRouterHarnessService
from intent_router_harness.workflow import HTTPWorkflowToolClient, load_workflow_settings

logger = logging.getLogger(__name__)


def build_service(settings: AppSettings) -> IntentRouterHarnessService:
    """Build the application service from deployable settings."""
    logger.info(
        "building service from settings spec_path=%s regression_suite_path=%s llm_env_file=%s workflow_env_file=%s skill_roots=%s",
        settings.spec_path,
        settings.regression_suite_path,
        settings.llm_env_file,
        settings.workflow_env_file,
        settings.skill_roots,
    )
    llm_client = _load_optional_llm_client(settings.llm_env_file)
    workflow_client = _load_optional_workflow_client(settings.workflow_env_file)
    return IntentRouterHarnessService.from_spec(
        settings.spec_path,
        skill_roots=settings.skill_roots,
        regression_suite_path=settings.regression_suite_path,
        llm_client=llm_client,
        workflow_client=workflow_client,
    )


def _load_optional_llm_client(env_file: str | Path | None) -> OpenAICompatibleLLMClient | None:
    if env_file is None:
        logger.info("LLM client disabled because llm_env_file is not configured")
        return None
    try:
        settings = load_llm_settings(env_file)
    except LLMConfigurationError:
        logger.warning("LLM client not configured env_file=%s", env_file)
        return None
    logger.info("LLM client configured env_file=%s model=%s base_url=%s", env_file, settings.model, settings.base_url)
    return OpenAICompatibleLLMClient(settings)


def _load_optional_workflow_client(env_file: str | Path | None) -> HTTPWorkflowToolClient | None:
    if env_file is None:
        logger.info("workflow client disabled because workflow_env_file is not configured")
        return None
    settings = load_workflow_settings(env_file)
    if settings is None:
        logger.info("workflow client not configured env_file=%s", env_file)
        return None
    logger.info("workflow client configured env_file=%s base_url=%s", env_file, settings.base_url)
    return HTTPWorkflowToolClient(settings)
