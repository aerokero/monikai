"""User Profile Management System"""
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field


@dataclass
class UserProfile:
    """Represents a user's profile"""
    id: str
    name: str
    birthday: str  # YYYY-MM-DD
    timezone: str
    interests: List[str] = field(default_factory=list)
    preferred_activities: List[str] = field(default_factory=list)
    communication_style: str = ""
    onboarding_completed_at: Optional[str] = None
    profile_version: int = 2
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        """Create from dictionary"""
        return cls(**data)

    def get_age(self) -> int:
        """Calculate age from birthday"""
        try:
            birth = datetime.fromisoformat(self.birthday)
            today = datetime.now()
            age = today.year - birth.year
            if (today.month, today.day) < (birth.month, birth.day):
                age -= 1
            return age
        except (ValueError, AttributeError):
            return 0

    def update_timestamp(self) -> None:
        """Update last modified timestamp"""
        self.updated_at = datetime.utcnow().isoformat()


class UserProfileManager:
    """Manages user profile creation, loading, and persistence"""

    def __init__(self, profile_path: str = "data/user_memory/profile.json"):
        self.profile_path = profile_path
        self.profile: Optional[UserProfile] = None

    def load_profile(self) -> Optional[UserProfile]:
        """Load profile from file"""
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r") as f:
                    data = json.load(f)
                    self.profile = UserProfile.from_dict(data)
                    return self.profile
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                print(f"Error loading profile: {e}")
                return None
        return None

    def save_profile(self, profile: Optional[UserProfile] = None) -> bool:
        """Save profile to file"""
        target_profile = profile or self.profile
        if not target_profile:
            return False

        try:
            os.makedirs(os.path.dirname(self.profile_path), exist_ok=True)
            target_profile.update_timestamp()
            with open(self.profile_path, "w") as f:
                json.dump(target_profile.to_dict(), f, indent=2)
            self.profile = target_profile
            return True
        except (IOError, OSError) as e:
            print(f"Error saving profile: {e}")
            return False

    def create_profile(
        self,
        user_id: str,
        name: str,
        birthday: str,
        timezone: str,
        interests: List[str],
        preferred_activities: List[str],
        communication_style: str = "",
    ) -> UserProfile:
        """Create a new user profile"""
        profile = UserProfile(
            id=user_id,
            name=name,
            birthday=birthday,
            timezone=timezone,
            interests=interests,
            preferred_activities=preferred_activities,
            communication_style=communication_style,
            onboarding_completed_at=datetime.utcnow().isoformat(),
        )
        self.profile = profile
        return profile

    def get_profile(self) -> Optional[UserProfile]:
        """Get current profile"""
        if not self.profile:
            self.load_profile()
        return self.profile

    def is_onboarding_complete(self) -> bool:
        """Check if onboarding is complete"""
        profile = self.get_profile()
        return profile is not None and profile.onboarding_completed_at is not None
