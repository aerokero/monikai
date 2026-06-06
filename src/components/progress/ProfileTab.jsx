import React, { useState, useEffect } from 'react';
import { Edit2, Save, X } from '../icons';
import { useProgression } from '../../contexts/ProgressionContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { formatTimestamp } from '../../utils/progressionTransformers';

/**
 * ProfileTab Component
 * 
 * Displays and allows editing of user profile:
 * - Name, Birthday, Timezone
 * - Interests, Preferred Activities
 * - Communication Style
 * 
 * Inline editing for each field.
 * Color binding to affection metric (blue → pink transition).
 */
const ProfileTab = () => {
  const { profile, metrics, updateProfile } = useProgression();
  const { t } = useLanguage();
  
  const [isEditing, setIsEditing] = useState(null); // Field being edited
  const [editValues, setEditValues] = useState({});
  const [isSaving, setIsSaving] = useState(false);
  const [showDebugPanel, setShowDebugPanel] = useState(false);

  // Initialize edit values from profile
  useEffect(() => {
    if (profile) {
      setEditValues({
        name: profile.name || '',
        birthday: profile.birthday || '',
        timezone: profile.timezone || '',
        interests: Array.isArray(profile.interests) ? profile.interests.join(', ') : '',
        preferred_activities: Array.isArray(profile.preferred_activities) ? profile.preferred_activities.join(', ') : '',
        communication_style: profile.communication_style || '',
      });
    }
  }, [profile]);

  if (!profile) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-white/50 text-center">
          <p>{t('common.loading') || 'Loading profile...'}</p>
        </div>
      </div>
    );
  }

  // Compute affection-based tint (0 = blue/cyan, 100 = pink/red)
  const affectionValue = metrics?.metrics?.find(m => m.name === 'affection')?.value || 0;
  const affectionProgress = Math.min(affectionValue / 100, 1);
  const tintColor = `hsl(${240 - (affectionProgress * 120)}, 100%, 50%)`; // 240° = cyan, 120° = red

  const handleEdit = (field) => {
    setIsEditing(field);
  };

  const handleCancel = () => {
    setIsEditing(null);
    // Reset to current profile value
    if (profile) {
      setEditValues({
        name: profile.name || '',
        birthday: profile.birthday || '',
        timezone: profile.timezone || '',
        interests: Array.isArray(profile.interests) ? profile.interests.join(', ') : '',
        preferred_activities: Array.isArray(profile.preferred_activities) ? profile.preferred_activities.join(', ') : '',
        communication_style: profile.communication_style || '',
      });
    }
  };

  const handleSave = async (field) => {
    setIsSaving(true);
    
    const updateData = {};
    
    // Parse arrays if necessary
    if (field === 'interests') {
      updateData.interests = editValues.interests?.split(',').map(i => i.trim()).filter(i => i) || [];
    } else if (field === 'preferred_activities') {
      updateData.preferred_activities = editValues.preferred_activities?.split(',').map(a => a.trim()).filter(a => a) || [];
    } else {
      updateData[field] = editValues[field];
    }

    updateProfile(updateData);
    
    setTimeout(() => {
      setIsEditing(null);
      setIsSaving(false);
    }, 800);
  };

  const ProfileField = ({ label, field, type = 'text', multiline = false }) => {
    const isCurrentlyEditing = isEditing === field;
    const value = editValues[field] || '';

    return (
      <div className="group">
        <div className="flex items-start justify-between mb-2">
          <label className="text-sm font-semibold text-white/70">{label}</label>
          {!isCurrentlyEditing && (
            <button
              onClick={() => handleEdit(field)}
              className="p-1 opacity-0 group-hover:opacity-100 transition-opacity text-white/50 hover:text-white hover:bg-white/10 rounded"
              title={t('common.edit') || 'Edit'}
            >
              <Edit2 size={14} />
            </button>
          )}
        </div>

        {isCurrentlyEditing ? (
          <div className="space-y-2">
            {multiline ? (
              <textarea
                value={value}
                onChange={(e) => setEditValues({ ...editValues, [field]: e.target.value })}
                className="w-full px-3 py-2 bg-white/5 border border-white/20 rounded text-white placeholder-white/30 focus:outline-none focus:border-white/40 text-sm"
                rows="4"
                placeholder={label}
              />
            ) : (
              <input
                type={type}
                value={value}
                onChange={(e) => setEditValues({ ...editValues, [field]: e.target.value })}
                className="w-full px-3 py-2 bg-white/5 border border-white/20 rounded text-white placeholder-white/30 focus:outline-none focus:border-white/40 text-sm"
                placeholder={label}
              />
            )}
            
            <div className="flex gap-2 justify-end">
              <button
                onClick={handleCancel}
                className="px-3 py-1.5 text-xs rounded bg-white/10 hover:bg-white/15 text-white/70 transition-colors"
              >
                <X size={14} className="inline mr-1" /> {t('common.cancel') || 'Cancel'}
              </button>
              <button
                onClick={() => handleSave(field)}
                disabled={isSaving}
                className="px-3 py-1.5 text-xs rounded bg-green-500/20 hover:bg-green-500/30 text-green-300 transition-colors disabled:opacity-50"
              >
                <Save size={14} className="inline mr-1" /> {t('common.save') || 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <div className="px-3 py-2 bg-white/5 border border-white/10 rounded text-white text-sm">
            {value || <span className="text-white/30">—</span>}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Affection-based warmth indicator */}
      <div className="p-4 rounded-lg bg-gradient-to-r from-blue-500/10 to-pink-500/10 border border-white/10">
        <p className="text-xs text-white/50 mb-3">Relationship Warmth</p>
        <div className="space-y-2">
          <div className="h-2 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${affectionProgress * 100}%`,
                backgroundColor: tintColor,
              }}
            />
          </div>
          <p className="text-xs text-white/50">
            Affection: {affectionValue.toFixed(0)} (influences profile warmth)
          </p>
        </div>
      </div>

      {/* Profile Info Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <ProfileField label={t('profile.name') || 'Name'} field="name" />
        <ProfileField label={t('profile.birthday') || 'Birthday'} field="birthday" type="date" />
        <ProfileField label={t('profile.timezone') || 'Timezone'} field="timezone" />
      </div>

      {/* Interests */}
      <ProfileField
        label={t('profile.interests') || 'Interests (comma-separated)'}
        field="interests"
        multiline={true}
      />

      {/* Preferred Activities */}
      <ProfileField
        label={t('profile.activities') || 'Preferred Activities (comma-separated)'}
        field="preferred_activities"
        multiline={true}
      />

      {/* Communication Style */}
      <ProfileField
        label={t('profile.style') || 'Communication Style'}
        field="communication_style"
        multiline={true}
      />

      {/* Metadata Section */}
      <div className="text-xs text-white/40 space-y-1 border-t border-white/10 pt-4">
        <p>Created: {formatTimestamp(profile.created_at)}</p>
        <p>Updated: {formatTimestamp(profile.updated_at)}</p>
        {profile.onboarding_completed_at && (
          <p>Onboarding: {formatTimestamp(profile.onboarding_completed_at)}</p>
        )}
      </div>

      {/* Hidden Debug Panel */}
      {showDebugPanel && (
        <div className="mt-6 p-3 bg-red-500/10 border border-red-500/20 rounded text-xs text-white/70 max-h-48 overflow-auto font-mono">
          <pre>{JSON.stringify(profile, null, 2)}</pre>
        </div>
      )}
      
      {/* Debug Toggle (Ctrl+Shift+P) */}
      <button
        onClick={() => setShowDebugPanel(!showDebugPanel)}
        onContextMenu={(e) => { e.preventDefault(); setShowDebugPanel(!showDebugPanel); }}
        className="text-xs text-white/20 hover:text-white/40 transition-colors"
      >
        {showDebugPanel ? 'Hide' : 'Show'} Debug Info
      </button>
    </div>
  );
};

export default ProfileTab;
