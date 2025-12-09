from typing import Literal, Union, Optional, List

# https://ai.google.dev/gemini-api/docs/rate-limits#current-rate-limits
SCoTModelType = Union[
    str,
    Literal[
        # This model is not available in the free plan.
        # Recommended for production environments for more tolerant rate limits.
        # [✨] https://ai.google.dev/gemini-api/docs/models#gemini-2.5-pro
        "gemini-2.5-pro",
        "gemini-2.5-pro-preview-06-05",
        "gemini-2.5-pro-preview-05-06",
        "gemini-2.5-pro-preview-03-25",
        # [🤷‍♂️] https://ai.google.dev/gemini-api/docs/models#gemini-2.5-flash
        "gemini-2.5-flash",
        # The following is a free experimental model that may fail at any time and is for demo only
        "gemini-2.5-pro-exp-03-25",
    ],
]

DEFAULT_SCOT_MODEL: SCoTModelType = "gemini-2.5-pro"

FastShotModelType = Union[
    str,
    Literal[
        # [✨] https://ai.google.dev/gemini-api/docs/models#gemini-2.5-flash
        "gemini-2.5-flash",
        # https://ai.google.dev/gemini-api/docs/models#gemini-2.0-flash
        "gemini-2.0-flash",
        # https://ai.google.dev/gemini-api/docs/models#gemini-2.5-flash-lite
        "gemini-2.5-flash-lite-preview-06-17",
        # https://ai.google.dev/gemini-api/docs/models#gemini-2.0-flash-lite
        "gemini-2.0-flash-lite",
    ],
]

THINKING_BUDGET_MODELS: List[Union[SCoTModelType, FastShotModelType]] = [
    "gemini-2.5-flash-lite-preview-06-17",
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-flash",
    "gemini-2.5-pro-preview-06-05",
    "gemini-2.5-pro",
]

DEFAULT_FAST_SHOT_MODEL: FastShotModelType = "gemini-2.5-flash"