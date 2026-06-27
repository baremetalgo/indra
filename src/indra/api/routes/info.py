from __future__ import annotations

from fastapi import APIRouter

from indra.api.deps import get_app_state

router = APIRouter(prefix="/info", tags=["info"])


@router.get("")
def get_info() -> dict:
    state = get_app_state()
    config = state.config
    return {
        "backend": config.model.backend,
        "model_path": config.model.model_path,
        "context_size": config.model.context_size,
        "gpu_layers": config.model.gpu_layers,
        "flash_attn": config.model.flash_attn,
        "max_llm_calls_medium": config.agent.max_llm_calls_medium,
        "max_steps": config.agent.max_steps,
    }
