import React, { useEffect, useState } from 'react';
import { User, Edit2, Save, X, Heart, Cake } from '../icons';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import useElementSize from '../../hooks/useElementSize';
import { useLanguage } from '../../contexts/LanguageContext';

const InputField = ({ label, type = 'text', value, onChange, placeholder = '' }) => (
  <div className="flex flex-col gap-2">
    <label className="text-xs font-medium text-white/70 uppercase tracking-wider">{label}</label>
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white placeholder-white/30 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-colors"
    />
  </div>
);

const SelectField = ({ label, value, onChange, options }) => (
  <div className="flex flex-col gap-2">
    <label className="text-xs font-medium text-white/70 uppercase tracking-wider">{label}</label>
    <select
      value={value}
      onChange={onChange}
      className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-colors"
    >
      <option value="">Select...</option>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  </div>
);

const Card = ({ title, icon: Icon, children, className = '' }) => (
  <section className={`rounded-[18px] border border-white/10 bg-black/20 p-4 ${className}`}>
    <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
      {Icon ? <Icon size={15} className="text-cyan-300" /> : null}
      <span>{title}</span>
    </div>
    {children}
  </section>
);

const ProfileShellPanel = ({ socket = null }) => {
  const { t } = useLanguage();
  const [panelRef] = useElementSize();
  const [isEditing, setIsEditing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [profile, setProfile] = useState({
    user_name: '',
    gender: '',
    birthday: '',
    location: '',
    occupation: '',
    interests: '',
    personality_traits: '',
  });

  const [formData, setFormData] = useState(profile);

  const emitWithAckTimeout = (eventName, payload, fallbackData = {}, timeoutMs = 4000) =>
    new Promise((resolve) => {
      let settled = false;
      const timeout = setTimeout(() => {
        if (!settled) {
          settled = true;
          resolve(fallbackData);
        }
      }, timeoutMs);

      socket.emit(eventName, payload, (response) => {
        if (!settled) {
          settled = true;
          clearTimeout(timeout);
          resolve(response || fallbackData);
        }
      });
    });

  // Load profile on mount
  useEffect(() => {
    let isMounted = true;

    if (!socket) {
      setIsLoading(false);
      return;
    }

    const loadProfile = async () => {
      const response = await emitWithAckTimeout('memory_get_profile', {}, { profile: {} });
      if (!isMounted) return;

      if (response && response.profile) {
        setProfile(response.profile);
        setFormData(response.profile);
      }
      setIsLoading(false);
    };

    loadProfile();

    return () => {
      isMounted = false;
    };
  }, [socket]);

  const handleEditToggle = () => {
    setIsEditing(!isEditing);
    if (!isEditing) {
      setFormData(profile);
    }
  };

  const handleSave = async () => {
    if (socket) {
      const response = await emitWithAckTimeout('memory_update_profile', { profile: formData }, { success: false });
      if (response && response.success) {
        setProfile(formData);
        setIsEditing(false);
      }
    }
  };

  const handleInputChange = (field) => (e) => {
    setFormData({
      ...formData,
      [field]: e.target.value,
    });
  };

  if (isEditing) {
    return (
      <ShellPanelFrame 
        title="Edit Profile" 
        icon={User}
        bodyClassName="min-h-0"
      >
        <div ref={panelRef} className="h-full min-h-0 p-3 overflow-y-auto">
          <div className="flex flex-col gap-4">
          <Card title="Personal Information" icon={User}>
            <div className="space-y-3">
              <InputField
                label="Name"
                value={formData.user_name}
                onChange={handleInputChange('user_name')}
                placeholder="Your name"
              />
              
              <SelectField
                label="Gender"
                value={formData.gender}
                onChange={handleInputChange('gender')}
                options={[
                  { value: 'M', label: 'Male' },
                  { value: 'F', label: 'Female' },
                  { value: 'Other', label: 'Other' },
                  { value: 'Prefer not to say', label: 'Prefer not to say' },
                ]}
              />

              <InputField
                label="Birthday"
                type="date"
                value={formData.birthday}
                onChange={handleInputChange('birthday')}
              />

              <InputField
                label="Location"
                value={formData.location}
                onChange={handleInputChange('location')}
                placeholder="City, Country"
              />

              <InputField
                label="Occupation"
                value={formData.occupation}
                onChange={handleInputChange('occupation')}
                placeholder="Your job or profession"
              />
            </div>
          </Card>

          <Card title="About You" icon={Heart}>
            <div className="space-y-3">
              <div className="flex flex-col gap-2">
                <label className="text-xs font-medium text-white/70 uppercase tracking-wider">Interests</label>
                <textarea
                  value={formData.interests}
                  onChange={handleInputChange('interests')}
                  placeholder="Your hobbies and interests..."
                  className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white placeholder-white/30 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-colors resize-none h-20"
                />
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-xs font-medium text-white/70 uppercase tracking-wider">Personality</label>
                <textarea
                  value={formData.personality_traits}
                  onChange={handleInputChange('personality_traits')}
                  placeholder="Describe your personality..."
                  className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-white placeholder-white/30 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-colors resize-none h-20"
                />
              </div>
            </div>
          </Card>

          {/* Action Buttons */}
          <div className="flex gap-2 sticky bottom-0 bg-black/40 -mx-4 px-4 py-3 border-t border-white/10">
            <button
              onClick={handleSave}
              className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-cyan-600 px-4 py-2 text-sm font-medium text-white hover:from-cyan-600 hover:to-cyan-700 transition-all"
            >
              <Save size={16} />
              Save Changes
            </button>
            <button
              onClick={handleEditToggle}
              className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-white/5 px-4 py-2 text-sm font-medium text-white hover:bg-white/10 transition-all"
            >
              <X size={16} />
              Cancel
            </button>
          </div>
          </div>
        </div>
      </ShellPanelFrame>
    );
  }

  return (
    <ShellPanelFrame 
      title="Profile" 
      icon={User}
      bodyClassName="min-h-0"
    >
      <div ref={panelRef} className="h-full min-h-0 p-3 overflow-y-auto">
        <div className="flex flex-col gap-4">
          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center py-12 text-white/60 text-sm">
              Loading profile...
            </div>
          )}

          {/* Error state - no socket */}
          {!isLoading && !socket && (
            <div className="flex items-center justify-center py-12 text-white/40 text-sm">
              Socket not connected
            </div>
          )}

          {/* Display Mode - Personal Info */}
          {!isLoading && socket && (
            <>
              <Card title="Personal Information" icon={User}>
              <div className="space-y-2">
                {profile.user_name && (
                  <div className="flex justify-between">
                    <span className="text-white/60 text-sm">Name:</span>
                    <span className="text-white font-medium text-sm">{profile.user_name}</span>
                  </div>
                )}
                {profile.gender && (
                  <div className="flex justify-between">
                    <span className="text-white/60 text-sm">Gender:</span>
                    <span className="text-white font-medium text-sm">{profile.gender}</span>
                  </div>
                )}
                {profile.birthday && (
                  <div className="flex justify-between items-center">
                    <span className="text-white/60 text-sm flex items-center gap-1">
                      <Cake size={14} />
                      Birthday:
                    </span>
                    <span className="text-white font-medium text-sm">{new Date(profile.birthday).toLocaleDateString()}</span>
                  </div>
                )}
                {profile.location && (
                  <div className="flex justify-between">
                    <span className="text-white/60 text-sm">Location:</span>
                    <span className="text-white font-medium text-sm">{profile.location}</span>
                  </div>
                )}
                {profile.occupation && (
                  <div className="flex justify-between">
                    <span className="text-white/60 text-sm">Occupation:</span>
                    <span className="text-white font-medium text-sm">{profile.occupation}</span>
                  </div>
                )}
              </div>
            </Card>

            {/* About You */}
            {profile.interests && (
              <Card title="Interests" icon={Heart}>
                <p className="text-white/80 text-sm whitespace-pre-wrap">{profile.interests}</p>
              </Card>
            )}

            {profile.personality_traits && (
              <Card title="Personality" icon={Heart}>
                <p className="text-white/80 text-sm whitespace-pre-wrap">{profile.personality_traits}</p>
              </Card>
            )}

            {/* Empty state */}
            {!profile.user_name && !profile.birthday && !profile.interests && (
              <div className="flex items-center justify-center py-12 text-white/40 text-sm">
                No profile information yet
              </div>
            )}

            {/* Edit Button */}
            <button
              onClick={handleEditToggle}
              className="sticky bottom-0 flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500/20 to-cyan-600/20 border border-cyan-500/50 px-4 py-2.5 text-sm font-medium text-cyan-300 hover:from-cyan-500/30 hover:to-cyan-600/30 transition-all mt-4"
            >
              <Edit2 size={16} />
              Edit Profile
            </button>
          </>
        )}
        </div>
      </div>
    </ShellPanelFrame>
  );
};

export default ProfileShellPanel;
