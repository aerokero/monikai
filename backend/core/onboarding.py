"""Onboarding Flow - Multi-turn conversation for profile collection"""
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any


class OnboardingFlow:
    """Manages the onboarding process"""

    ONBOARDING_STEPS = [
        {
            "step": 1,
            "field": "name",
            "prompt": "Hi there! What's your name?",
            "validation": lambda x: len(x.strip()) > 0 and len(x) < 100
        },
        {
            "step": 2,
            "field": "birthday",
            "prompt": "When were you born? (YYYY-MM-DD)",
            "validation": lambda x: _validate_date(x)
        },
        {
            "step": 3,
            "field": "timezone",
            "prompt": "What's your timezone? (e.g., Europe/Warsaw, America/New_York)",
            "validation": lambda x: len(x.strip()) > 0
        },
        {
            "step": 4,
            "field": "interests",
            "prompt": "What are your main interests? (comma-separated: e.g., gaming, music, art)",
            "validation": lambda x: len(x.strip()) > 0,
            "post_process": lambda x: [i.strip() for i in x.split(",")]
        },
        {
            "step": 5,
            "field": "preferred_activities",
            "prompt": "What activities do you prefer most? (comma-separated. Options: conversation, gaming, watching, learning, fitness, music, art, reading)",
            "validation": lambda x: len(x.strip()) > 0,
            "post_process": lambda x: [i.strip().lower() for i in x.split(",") if i.strip().lower() in ["conversation", "gaming", "watching", "learning", "fitness", "music", "art", "reading"]]
        },
        {
            "step": 6,
            "field": "communication_style",
            "prompt": "How do you prefer to communicate? (e.g., casual, formal, humorous, thoughtful)",
            "validation": lambda x: len(x.strip()) > 0
        }
    ]

    def __init__(self):
        self.current_step = 0
        self.collected_data: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.utcnow().isoformat()
        }
        self.completed = False

    def get_current_prompt(self) -> Optional[str]:
        """Get the current step's prompt"""
        if self.current_step >= len(self.ONBOARDING_STEPS):
            return None
        return self.ONBOARDING_STEPS[self.current_step]["prompt"]

    def process_response(self, user_input: str) -> Dict[str, Any]:
        """
        Process user's response to current onboarding step.
        Returns: {
            "valid": bool,
            "message": str,
            "next_prompt": str or None,
            "completed": bool
        }
        """
        if self.current_step >= len(self.ONBOARDING_STEPS):
            return {
                "valid": False,
                "message": "Onboarding already completed",
                "completed": True
            }

        step_config = self.ONBOARDING_STEPS[self.current_step]
        field = step_config["field"]
        validation = step_config["validation"]

        # Validate input
        if not user_input or not validation(user_input):
            return {
                "valid": False,
                "message": f"Invalid input for {field}. Please try again.",
                "next_prompt": step_config["prompt"],
                "completed": False
            }

        # Process input
        value = user_input.strip()

        # Apply post-processing if defined
        if "post_process" in step_config:
            value = step_config["post_process"](value)

        self.collected_data[field] = value

        # Move to next step
        self.current_step += 1

        # Check if onboarding is complete
        if self.current_step >= len(self.ONBOARDING_STEPS):
            self.collected_data["onboarding_completed_at"] = datetime.utcnow().isoformat()
            self.completed = True
            return {
                "valid": True,
                "message": f"Perfect! Nice to meet you, {self.collected_data.get('name')}! Let's start our journey together.",
                "next_prompt": None,
                "completed": True
            }

        # Get next prompt
        next_prompt = self.get_current_prompt()
        return {
            "valid": True,
            "message": "Got it!",
            "next_prompt": next_prompt,
            "completed": False
        }

    def get_collected_data(self) -> Dict[str, Any]:
        """Get all collected profile data"""
        return self.collected_data.copy()

    def is_complete(self) -> bool:
        """Check if onboarding is complete"""
        return self.completed

    def get_progress(self) -> Dict[str, Any]:
        """Get onboarding progress"""
        return {
            "current_step": self.current_step,
            "total_steps": len(self.ONBOARDING_STEPS),
            "progress_pct": (self.current_step / len(self.ONBOARDING_STEPS)) * 100,
            "completed": self.completed
        }


def _validate_date(date_str: str) -> bool:
    """Validate YYYY-MM-DD format"""
    try:
        datetime.fromisoformat(date_str)
        return True
    except (ValueError, TypeError):
        return False


class OnboardingManager:
    """Manages onboarding sessions"""

    def __init__(self):
        self.active_flows: Dict[str, OnboardingFlow] = {}

    def start_onboarding(self, user_id: str = None) -> str:
        """Start a new onboarding flow. Returns flow ID."""
        if not user_id:
            user_id = str(uuid.uuid4())

        flow = OnboardingFlow()
        flow.collected_data["id"] = user_id
        self.active_flows[user_id] = flow

        return user_id

    def get_flow(self, user_id: str) -> Optional[OnboardingFlow]:
        """Get onboarding flow for a user"""
        return self.active_flows.get(user_id)

    def process_response(self, user_id: str, user_input: str) -> Dict[str, Any]:
        """Process response in onboarding flow"""
        flow = self.get_flow(user_id)
        if not flow:
            return {"error": "No active onboarding flow"}

        result = flow.process_response(user_input)

        # If completed, remove from active flows
        if flow.is_complete():
            del self.active_flows[user_id]

        return result

    def complete_onboarding(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get completed onboarding data"""
        flow = self.get_flow(user_id)
        if flow and flow.is_complete():
            data = flow.get_collected_data()
            del self.active_flows[user_id]
            return data

        return None
