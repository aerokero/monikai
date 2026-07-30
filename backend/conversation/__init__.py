"""Text-first conversation authoring primitives."""

from .author import AUTHOR_INSTRUCTION, ResponseBrief, parse_response_brief
from .context import ConversationContextCompiler
from .models import CompiledConversationContext
from .providers import (
    GeminiTextProvider,
    TextGenerationRequest,
    TextModelProvider,
    ToolPlanningRequest,
)
from .routing import requires_capability_runtime
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
from .validator import ConversationResponseValidator

__all__ = [
    "AUTHOR_INSTRUCTION",
    "CompiledConversationContext",
    "ConversationContextCompiler",
    "ConversationResponseValidator",
    "ConversationToolExecutor",
    "ConversationToolDefinition",
    "ConversationToolRequest",
    "ConversationToolResult",
    "CONVERSATION_TOOL_DEFINITIONS",
    "GeminiTextProvider",
    "GeminiSpeechSynthesizer",
    "ResponseBrief",
    "SpeechSynthesisRequest",
    "SpeechSynthesizer",
    "SynthesizedSpeech",
    "TextGenerationRequest",
    "TextModelProvider",
    "ToolTurnOutcome",
    "ToolPlanningRequest",
    "parse_response_brief",
    "plan_read_only_tool",
    "validate_planned_tool_request",
    "requires_capability_runtime",
]
