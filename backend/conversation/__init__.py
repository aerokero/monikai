"""Text-first conversation authoring primitives."""

from .providers import (
    GeminiTextProvider,
    TextGenerationRequest,
    TextModelProvider,
    ToolPlanningRequest,
)
from .speech import (
    GeminiSpeechSynthesizer,
    SpeechSynthesisRequest,
    SpeechSynthesizer,
    SynthesizedSpeech,
)
from .tools import (
    CONVERSATION_TOOL_DEFINITIONS,
    ConversationToolDefinition,
    ConversationToolExecutor,
    ConversationToolRequest,
    ConversationToolResult,
    ToolTurnOutcome,
    plan_read_only_tool,
    validate_planned_tool_request,
)

__all__ = [
    "ConversationToolExecutor",
    "ConversationToolDefinition",
    "ConversationToolRequest",
    "ConversationToolResult",
    "CONVERSATION_TOOL_DEFINITIONS",
    "GeminiTextProvider",
    "GeminiSpeechSynthesizer",
    "SpeechSynthesisRequest",
    "SpeechSynthesizer",
    "SynthesizedSpeech",
    "TextGenerationRequest",
    "TextModelProvider",
    "ToolTurnOutcome",
    "ToolPlanningRequest",
    "plan_read_only_tool",
    "validate_planned_tool_request",
]
