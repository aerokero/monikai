"""
REST API Endpoints for Progression System
To be integrated into server.py
"""
from flask import Blueprint, request, jsonify
from datetime import datetime


def create_progression_endpoints(progression_system):
    """
    Create Flask blueprint with progression endpoints.
    progression_system: IntegratedProgressionSystem instance
    """
    bp = Blueprint('progression', __name__, url_prefix='/api/progression')

    @bp.route('/profile', methods=['GET'])
    def get_profile():
        """Get user profile"""
        profile = progression_system.profile_manager.get_profile()
        if not profile:
            return jsonify({"error": "No profile loaded"}), 404
        return jsonify(profile.to_dict()), 200

    @bp.route('/profile', methods=['POST'])
    def update_profile():
        """Update user profile"""
        data = request.json or {}
        profile = progression_system.profile_manager.get_profile()
        if not profile:
            return jsonify({"error": "No profile loaded"}), 404

        # Update allowed fields
        allowed_fields = ["interests", "preferred_activities", "communication_style"]
        for field in allowed_fields:
            if field in data:
                setattr(profile, field, data[field])

        progression_system.profile_manager.save_profile(profile)
        return jsonify(profile.to_dict()), 200

    @bp.route('/metrics', methods=['GET'])
    def get_metrics():
        """Get relationship metrics"""
        metrics = progression_system.metrics_engine.get_metrics_state()
        progress = progression_system.metrics_engine.get_recommendation_progress()
        return jsonify({
            "metrics": metrics,
            "progress": progress
        }), 200

    @bp.route('/quests/today', methods=['GET'])
    def get_today_quests():
        """Get today's quests by slot (morning/afternoon/evening)"""
        quests = progression_system.quest_system.get_active_quests()
        return jsonify({
            "quests": quests,
            "total_active": len(quests)
        }), 200

    @bp.route('/quests/<slot>', methods=['GET'])
    def get_quests_by_slot(slot):
        """Get quests for a specific slot"""
        quests = progression_system.quest_system.get_quests_by_slot(slot)
        return jsonify({
            "slot": slot,
            "quests": quests,
            "count": len(quests)
        }), 200

    @bp.route('/quests/<quest_id>/complete', methods=['POST'])
    def complete_quest(quest_id):
        """Mark a quest as complete"""
        for quest in progression_system.quest_system.active_quests:
            if quest.id == quest_id:
                quest.mark_completed()
                progression_system.save_if_needed()
                return jsonify({
                    "quest_id": quest_id,
                    "status": "completed",
                    "reward_xp": quest.reward_xp
                }), 200

        return jsonify({"error": "Quest not found"}), 404

    @bp.route('/achievements', methods=['GET'])
    def get_achievements():
        """Get achievement status"""
        unlocked = progression_system.achievement_tracker.get_unlocked_achievements()
        locked = progression_system.achievement_tracker.get_locked_achievements()
        progress = progression_system.achievement_tracker.get_achievements_progress()

        return jsonify({
            "unlocked": unlocked,
            "locked": locked,
            "progress": progress
        }), 200

    @bp.route('/achievements/unlocked', methods=['GET'])
    def get_unlocked_achievements():
        """Get only unlocked achievements"""
        unlocked = progression_system.achievement_tracker.get_unlocked_achievements()
        return jsonify(unlocked), 200

    @bp.route('/unlocks', methods=['GET'])
    def get_unlocks():
        """Get unlock status"""
        active = progression_system.unlock_tracker.get_active_unlocks()
        available = progression_system.unlock_tracker.get_available_unlocks()
        return jsonify({
            "active": active,
            "available": available,
            "total_active": len(active)
        }), 200

    @bp.route('/unlocks/active', methods=['GET'])
    def get_active_unlocks():
        """Get active/unlocked features"""
        unlocks = progression_system.unlock_tracker.get_active_unlocks()
        return jsonify(unlocks), 200

    @bp.route('/narrative/context', methods=['GET'])
    def get_narrative_context():
        """Get narrative/story context"""
        context = progression_system.narrative_engine.get_story_context()
        return jsonify(context), 200

    @bp.route('/narrative/flags', methods=['GET'])
    def get_story_flags():
        """Get all story flags"""
        flags = progression_system.narrative_engine.get_all_flags()
        return jsonify(flags), 200

    @bp.route('/seasonal/events', methods=['GET'])
    def get_seasonal_events():
        """Get active seasonal events"""
        active = progression_system.seasonal_executor.check_active_events()
        return jsonify({
            "active_events": active,
            "count": len(active)
        }), 200

    @bp.route('/notifications', methods=['GET'])
    def get_notifications():
        """Get pending notifications"""
        notifications = progression_system.get_pending_notifications()
        return jsonify({
            "notifications": notifications,
            "count": len(notifications)
        }), 200

    @bp.route('/state', methods=['GET'])
    def get_full_state():
        """Get complete progression state"""
        state = progression_system.get_progression_state()
        return jsonify(state), 200

    @bp.route('/onboarding/start', methods=['POST'])
    def start_onboarding():
        """Start onboarding flow"""
        message, prompt = progression_system.start_onboarding()
        return jsonify({
            "message": message,
            "prompt": prompt,
            "step": 1,
            "total_steps": 6
        }), 200

    @bp.route('/onboarding/response', methods=['POST'])
    def onboarding_response():
        """Process onboarding response"""
        data = request.json or {}
        user_input = data.get("input", "")

        result = progression_system.process_onboarding_response(user_input)

        if result.get("completed"):
            return jsonify({
                "completed": True,
                "message": result.get("message"),
                "profile_created": True
            }), 200
        else:
            return jsonify({
                "valid": result.get("valid"),
                "message": result.get("message"),
                "prompt": result.get("next_prompt"),
                "completed": False
            }), 200

    return bp
