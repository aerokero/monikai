import React, { useEffect, useState } from 'react';
import { User, Edit2, Save, X, Heart, Cake } from '../icons';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import useElementSize from '../../hooks/useElementSize';
import { useLanguage } from '../../contexts/LanguageContext';
import { SectionLabel, Card, SummaryField, TextField, SelectField, TextAreaField } from '../shared/panelPrimitives';

const Section = ({ title, icon: Icon, children }) => (
  <div>
    <SectionLabel>
      <span className="flex items-center gap-1.5">
        {Icon && <Icon size={11} className="text-[#de9d50]/70" />}
        {title}
      </span>
    </SectionLabel>
    <Card className="px-4">{children}</Card>
  </div>
);

const GENDER_OPTIONS = [
  { value: '', label: '—' },
  { value: 'M', label: 'Male' },
  { value: 'F', label: 'Female' },
  { value: 'Other', label: 'Other' },
  { value: 'Prefer not to say', label: 'Prefer not to say' },
];

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
      const timeout = setTimeout(() => { if (!settled) { settled = true; resolve(fallbackData); } }, timeoutMs);
      socket.emit(eventName, payload, (response) => {
        if (!settled) { settled = true; clearTimeout(timeout); resolve(response || fallbackData); }
      });
    });

  useEffect(() => {
    let isMounted = true;
    if (!socket) { setIsLoading(false); return; }
    (async () => {
      const response = await emitWithAckTimeout('memory_get_profile', {}, { profile: {} });
      if (!isMounted) return;
      if (response?.profile) { setProfile(response.profile); setFormData(response.profile); }
      setIsLoading(false);
    })();
    return () => { isMounted = false; };
  }, [socket]);

  const handleEditToggle = () => {
    setIsEditing((v) => !v);
    if (!isEditing) setFormData(profile);
  };

  const handleSave = async () => {
    if (!socket) return;
    const response = await emitWithAckTimeout('memory_update_profile', { profile: formData }, { success: false });
    if (response?.success) { setProfile(formData); setIsEditing(false); }
  };

  const set = (field) => (e) => setFormData((prev) => ({ ...prev, [field]: e.target.value }));

  /* ── Edit mode ─────────────────────────────────────────────────── */
  if (isEditing) {
    return (
      <ShellPanelFrame icon={User} title="Edit Profile">
        <div ref={panelRef} className="flex-1 overflow-y-auto px-6 py-4 pb-10 custom-scrollbar">
          <div className="flex flex-col gap-5">
            <Section title="Personal" icon={User}>
              <div className="space-y-3.5 py-4">
                <TextField label="Name" value={formData.user_name} onChange={set('user_name')} placeholder="Your name" />
                <SelectField label="Gender" value={formData.gender} onChange={set('gender')} options={GENDER_OPTIONS} />
                <TextField label="Birthday" type="date" value={formData.birthday} onChange={set('birthday')} />
                <TextField label="Location" value={formData.location} onChange={set('location')} placeholder="City, Country" />
                <TextField label="Occupation" value={formData.occupation} onChange={set('occupation')} placeholder="Your job or profession" />
              </div>
            </Section>

            <Section title="About you" icon={Heart}>
              <div className="space-y-3.5 py-4">
                <TextAreaField
                  label="Interests"
                  value={formData.interests}
                  onChange={set('interests')}
                  placeholder="Your hobbies and interests..."
                  className="h-20"
                />
                <TextAreaField
                  label="Personality"
                  value={formData.personality_traits}
                  onChange={set('personality_traits')}
                  placeholder="Describe your personality..."
                  className="h-20"
                />
              </div>
            </Section>

            <div className="flex gap-2 pt-1">
              <button
                onClick={handleSave}
                className="flex-1 rounded-full bg-[#de9d50] py-2.5 text-xs font-bold text-[#16100d] transition-all hover:brightness-110"
              >
                <Save size={12} className="mr-1.5 inline" />
                Save Changes
              </button>
              <button
                onClick={handleEditToggle}
                className="flex-1 rounded-full border border-[#3c2e26] bg-[#1e1612] py-2.5 text-xs font-semibold text-[#8c7769] transition-colors hover:text-[#f5e6d3]"
              >
                <X size={12} className="mr-1.5 inline" />
                Cancel
              </button>
            </div>
          </div>
        </div>
      </ShellPanelFrame>
    );
  }

  /* ── View mode ─────────────────────────────────────────────────── */
  return (
    <ShellPanelFrame
      icon={User}
      title={profile.user_name || 'Profile'}
      actions={(
        <button
          onClick={handleEditToggle}
          className="rounded-full border border-[#3c2e26] bg-[#1e1612] px-3 py-1.5 text-xs text-[#8c7769] transition-colors hover:border-[#de9d50] hover:text-[#de9d50]"
        >
          <Edit2 size={11} className="mr-1.5 inline" />
          Edit
        </button>
      )}
    >
      <div ref={panelRef} className="flex-1 overflow-y-auto px-6 py-4 pb-10 custom-scrollbar">
        {isLoading && (
          <div className="flex items-center justify-center py-12 text-sm text-[#8c7769]/50">
            Loading…
          </div>
        )}
        {!isLoading && !socket && (
          <div className="flex items-center justify-center py-12 text-sm text-[#8c7769]/40">
            {t('system.disconnected')}
          </div>
        )}
        {!isLoading && socket && (
          <div className="flex flex-col gap-5">
            <Section title="Personal" icon={User}>
              {profile.user_name && <SummaryField label="Name" value={profile.user_name} />}
              {profile.gender && <SummaryField label="Gender" value={profile.gender} />}
              {profile.birthday && (
                <SummaryField
                  label={<span className="flex items-center gap-1"><Cake size={11} />Birthday</span>}
                  value={new Date(profile.birthday).toLocaleDateString()}
                />
              )}
              {profile.location && <SummaryField label="Location" value={profile.location} />}
              {profile.occupation && <SummaryField label="Occupation" value={profile.occupation} />}
              {!profile.user_name && !profile.birthday && !profile.location && !profile.occupation && (
                <p className="py-4 text-sm text-[#8c7769]/70">No information yet.</p>
              )}
            </Section>

            {profile.interests && (
              <Section title="Interests" icon={Heart}>
                <p className="py-4 text-sm leading-relaxed text-[#8c7769]">{profile.interests}</p>
              </Section>
            )}

            {profile.personality_traits && (
              <Section title="Personality" icon={Heart}>
                <p className="py-4 text-sm leading-relaxed text-[#8c7769]">{profile.personality_traits}</p>
              </Section>
            )}
          </div>
        )}
      </div>
    </ShellPanelFrame>
  );
};

export default ProfileShellPanel;
