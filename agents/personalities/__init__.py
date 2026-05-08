"""人格系统

定义了5种不同人格的 System Prompt
"""
from .rational import get_rational_prompt, RATIONAL_SYSTEM_PROMPT
from .aggressive import get_agitator_prompt, AGITATOR_SYSTEM_PROMPT
from .hesitant import get_conservative_prompt, CONSERVATIVE_SYSTEM_PROMPT
from .follower import get_impulsive_prompt, IMPULSIVE_SYSTEM_PROMPT
from .slacker import get_slacker_prompt, SLACKER_SYSTEM_PROMPT


PERSONALITY_PROMPTS = {
    "rational": RATIONAL_SYSTEM_PROMPT,
    "agitative": AGITATOR_SYSTEM_PROMPT,
    "conservative": CONSERVATIVE_SYSTEM_PROMPT,
    "impulsive": IMPULSIVE_SYSTEM_PROMPT,
    "slacker": SLACKER_SYSTEM_PROMPT,
}


def get_personality_prompt(personality: str) -> str:
    """获取人格对应的 System Prompt"""
    return PERSONALITY_PROMPTS.get(personality, RATIONAL_SYSTEM_PROMPT)


__all__ = [
    "get_rational_prompt",
    "get_agitator_prompt",
    "get_conservative_prompt",
    "get_impulsive_prompt",
    "get_slacker_prompt",
    "get_personality_prompt",
    "PERSONALITY_PROMPTS",
]
