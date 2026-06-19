from app.prompts.final_aggregation import (
    FINAL_AGGREGATION_SYSTEM_PROMPT,
    build_aggregation_user_prompt,
)
from app.prompts.segment_comparison import (
    SEGMENT_SYSTEM_PROMPT,
    build_comparison_user_prompt,
)
from app.prompts.segmentation import (
    SEGMENTATION_SYSTEM_PROMPT,
    build_segmentation_user_prompt,
)


class Prompts:
    segmentation_system = SEGMENTATION_SYSTEM_PROMPT
    segment_comparison_system = SEGMENT_SYSTEM_PROMPT
    final_aggregation_system = FINAL_AGGREGATION_SYSTEM_PROMPT

    build_segmentation_user = staticmethod(build_segmentation_user_prompt)
    build_comparison_user = staticmethod(build_comparison_user_prompt)
    build_aggregation_user = staticmethod(build_aggregation_user_prompt)


prompts = Prompts()
