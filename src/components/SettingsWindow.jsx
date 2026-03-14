import React, { useRef, useState } from 'react';
import { X, Upload, Mic, Speaker, Video, Shield, Cpu, Globe, Lock, Package, RefreshCw, Trash2 } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const CONFIGURABLE_TOOLS = [
  'cancel_reminder',
  'control_light',
  'clear_work_memory',
  'notes_set',
  'run_web_agent',
  'run_openclaw_agent',
  'manage_agent_job',
  'run_skill_command',
  'list_skills',
  'get_skill',
  'refresh_skills',
  'write_file'
];

const SettingsWindow = ({
  micDevices,
  speakerDevices,
  webcamDevices,
  selectedMicId,
  setSelectedMicId,
  selectedSpeakerId,
  setSelectedSpeakerId,
  selectedWebcamId,
  setSelectedWebcamId,
  isCameraFlipped,
  setIsCameraFlipped,
  toolPermissions = {},
  onTogglePermission,
  handleFileUpload,
  skills = [],
  skillsLoading = false,
  skillsActionBusy = false,
  onRefreshSkills,
  onUploadSkillZip,
  onInstallSkillSource,
  onUninstallSkill,
  onClose
}) => {
  const { t, language, setLanguage } = useLanguage();
  const [isSkillDropActive, setIsSkillDropActive] = useState(false);
  const [skillSource, setSkillSource] = useState('');
  const [skillNameFilter, setSkillNameFilter] = useState('');
  const [skillAgent, setSkillAgent] = useState('codex');
  const [skillGlobalScope, setSkillGlobalScope] = useState(false);
  const skillFileInputRef = useRef(null);
  const memoryFileInputRef = useRef(null);

  const handleSkillFiles = (files) => {
    const first = files && files[0];
    if (!first) return;
    if (onUploadSkillZip) {
      onUploadSkillZip(first);
    }
    if (skillFileInputRef.current) {
      skillFileInputRef.current.value = '';
    }
  };

  const handleMemoryFiles = (e) => {
    if (handleFileUpload) {
      handleFileUpload(e);
    }
    if (memoryFileInputRef.current) {
      memoryFileInputRef.current.value = '';
    }
  };

  const submitSkillSource = () => {
    const source = skillSource.trim();
    if (!source || !onInstallSkillSource) return;
    onInstallSkillSource({
      source,
      skillName: skillNameFilter.trim(),
      agent: skillAgent,
      globalScope: skillGlobalScope,
      copyFiles: true,
    });
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-2xl bg-black/60 backdrop-blur-2xl border border-white/10 rounded-xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden">
        
        {/* Header - Fixed */}
        <div className="flex items-center justify-between p-6 border-b border-white/10 bg-white/5 shrink-0">
          <h2 className="text-xl font-light tracking-wider text-white flex items-center gap-3">
            <Cpu size={20} className="text-white" />
            {t('settings.title')}
          </h2>
          <button 
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg text-white/50 hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content - Scrollable */}
        <div className="p-6 overflow-y-auto space-y-8 custom-scrollbar">
          
          {/* Language */}
          <section className="space-y-4">
            <h3 className="text-sm font-medium text-white uppercase tracking-widest flex items-center gap-2">
              <Globe size={16} />
              {t('settings.language')}
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setLanguage('en')}
                className={`p-3 rounded-lg border text-left transition-all ${
                  language === 'en' 
                    ? 'bg-white/20 border-white/50 text-white' 
                    : 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10'
                }`}
              >
                English
              </button>
              <button
                onClick={() => setLanguage('pl')}
                className={`p-3 rounded-lg border text-left transition-all ${
                  language === 'pl' 
                    ? 'bg-white/20 border-white/50 text-white' 
                    : 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10'
                }`}
              >
                Polski
              </button>
            </div>
          </section>

          {/* Devices */}
          <section className="space-y-4">
            <h3 className="text-sm font-medium text-white uppercase tracking-widest flex items-center gap-2">
              <Mic size={16} />
              {t('settings.microphone')}
            </h3>
            <select
              value={selectedMicId}
              onChange={(e) => setSelectedMicId(e.target.value)}
              className="w-full bg-black border border-white/20 rounded-lg p-3 text-white focus:border-white focus:outline-none"
            >
              {micDevices.map(device => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label || `Microphone ${device.deviceId.slice(0, 5)}...`}
                </option>
              ))}
            </select>
          </section>

          <section className="space-y-4">
            <h3 className="text-sm font-medium text-white uppercase tracking-widest flex items-center gap-2">
              <Speaker size={16} />
              {t('settings.speaker')}
            </h3>
            <select
              value={selectedSpeakerId}
              onChange={(e) => setSelectedSpeakerId(e.target.value)}
              className="w-full bg-black border border-white/20 rounded-lg p-3 text-white focus:border-white focus:outline-none"
            >
              {speakerDevices.map(device => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label || `Speaker ${device.deviceId.slice(0, 5)}...`}
                </option>
              ))}
            </select>
          </section>

          <section className="space-y-4">
            <h3 className="text-sm font-medium text-white uppercase tracking-widest flex items-center gap-2">
              <Video size={16} />
              {t('settings.camera')}
            </h3>
            <select
              value={selectedWebcamId}
              onChange={(e) => setSelectedWebcamId(e.target.value)}
              className="w-full bg-black border border-white/20 rounded-lg p-3 text-white focus:border-white focus:outline-none"
            >
              {webcamDevices.map(device => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label || `Camera ${device.deviceId.slice(0, 5)}...`}
                </option>
              ))}
            </select>

            <div className="flex items-center justify-between bg-white/5 p-3 rounded-lg border border-white/10">
              <span className="text-white/80">{t('settings.mirror_vision')}</span>
              <button
                onClick={() => setIsCameraFlipped(!isCameraFlipped)}
                className={`w-12 h-6 rounded-full transition-colors relative ${
                  isCameraFlipped ? 'bg-white' : 'bg-white/20'
                }`}
              >
                <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                  isCameraFlipped ? 'left-7' : 'left-1'
                }`} />
              </button>
            </div>
          </section>

          {/* Security / Permissions */}
          <section className="space-y-4">
            <h3 className="text-sm font-medium text-white uppercase tracking-widest flex items-center gap-2">
              <Lock size={16} />
              {t('settings.security')}
            </h3>
            
            <div className="bg-white/5 p-4 rounded-lg border border-white/10 space-y-4">
              <p className="text-xs text-white/60">{t('settings.permissions')}</p>
              <div className="space-y-3">
                {Object.entries(toolPermissions)
                  .filter(([key]) => CONFIGURABLE_TOOLS.includes(key))
                  .map(([key, val]) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-sm text-white/80 capitalize font-mono">{key.replace(/_/g, ' ')}</span>
                    <button
                      onClick={() => onTogglePermission && onTogglePermission(key)}
                      className={`w-10 h-5 rounded-full transition-colors relative ${
                        val ? 'bg-white' : 'bg-white/10'
                      }`}
                    >
                      <div className={`absolute top-1 w-3 h-3 rounded-full bg-white transition-transform ${
                        val ? 'left-6' : 'left-1'
                      }`} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Skills */}
          <section className="space-y-4">
            <h3 className="text-sm font-medium text-white uppercase tracking-widest flex items-center gap-2">
              <Package size={16} />
              Skills
            </h3>

            <div className="bg-white/5 p-4 rounded-lg border border-white/10 space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-xs text-white/60">
                  Installed skills: {skills.length}
                </p>
                <button
                  onClick={() => onRefreshSkills && onRefreshSkills()}
                  disabled={skillsLoading || skillsActionBusy}
                  className="px-3 py-1.5 rounded-md border border-white/15 text-xs text-white/80 hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <RefreshCw size={12} />
                  Refresh
                </button>
              </div>

              <div className="p-4 rounded-lg border border-white/10 bg-black/30 space-y-3">
                <div className="min-w-0">
                  <p className="text-sm text-white/90 font-medium">Install from skills.sh source</p>
                  <p className="text-xs text-white/50">Uses `npx skills add ...` for repo/package installs.</p>
                </div>
                <input
                  value={skillSource}
                  onChange={(e) => setSkillSource(e.target.value)}
                  placeholder="https://github.com/vercel-labs/skills"
                  disabled={skillsActionBusy}
                  className="w-full bg-black border border-white/20 rounded-lg p-3 text-sm text-white focus:border-white focus:outline-none disabled:opacity-50"
                />
                <input
                  value={skillNameFilter}
                  onChange={(e) => setSkillNameFilter(e.target.value)}
                  placeholder="Optional skill name, e.g. find-skills"
                  disabled={skillsActionBusy}
                  className="w-full bg-black border border-white/20 rounded-lg p-3 text-sm text-white focus:border-white focus:outline-none disabled:opacity-50"
                />
                <div className="grid grid-cols-2 gap-3">
                  <select
                    value={skillAgent}
                    onChange={(e) => setSkillAgent(e.target.value)}
                    disabled={skillsActionBusy}
                    className="w-full bg-black border border-white/20 rounded-lg p-3 text-sm text-white focus:border-white focus:outline-none disabled:opacity-50"
                  >
                    <option value="codex">Codex</option>
                    <option value="openclaw">OpenClaw</option>
                  </select>
                  <label className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 text-sm text-white/80">
                    <input
                      type="checkbox"
                      checked={skillGlobalScope}
                      onChange={(e) => setSkillGlobalScope(e.target.checked)}
                      disabled={skillsActionBusy}
                      className="accent-white"
                    />
                    Install globally
                  </label>
                </div>
                <button
                  onClick={submitSkillSource}
                  disabled={skillsActionBusy || !skillSource.trim()}
                  className="px-3 py-2 rounded-md border border-white/15 text-sm text-white/90 hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Install from source
                </button>
              </div>

              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsSkillDropActive(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setIsSkillDropActive(false);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsSkillDropActive(false);
                  handleSkillFiles(e.dataTransfer?.files);
                }}
                className={`p-4 border-2 border-dashed rounded-lg transition-all ${
                  isSkillDropActive
                    ? 'border-white/70 bg-white/10'
                    : 'border-white/20 bg-black/30'
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-white/90 font-medium">Install from ZIP</p>
                    <p className="text-xs text-white/50">Drag & drop `.zip` or choose file</p>
                  </div>
                  <button
                    onClick={() => skillFileInputRef.current?.click()}
                    disabled={skillsActionBusy}
                    className="px-3 py-1.5 rounded-md border border-white/15 text-xs text-white/80 hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Choose ZIP
                  </button>
                </div>
                <input
                  ref={skillFileInputRef}
                  type="file"
                  accept=".zip,application/zip,application/x-zip-compressed"
                  className="hidden"
                  onChange={(e) => handleSkillFiles(e.target.files)}
                />
              </div>

              <div className="max-h-52 overflow-y-auto space-y-2 pr-1">
                {skillsLoading && (
                  <div className="text-xs text-white/60">Loading skills...</div>
                )}
                {!skillsLoading && skills.length === 0 && (
                  <div className="text-xs text-white/50">No skills found.</div>
                )}
                {!skillsLoading && skills.map((skill) => (
                  <div key={`${skill.name}-${skill.path}`} className="p-2.5 rounded-md border border-white/10 bg-black/30">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm text-white/90 truncate flex items-center gap-2">
                          <span>{skill.name}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                            skill.enabled === false
                              ? 'text-red-200 border-red-400/30 bg-red-500/10'
                              : skill.eligible
                              ? 'text-emerald-200 border-emerald-400/30 bg-emerald-500/10'
                              : 'text-amber-200 border-amber-400/30 bg-amber-500/10'
                          }`}>
                            {skill.enabled === false ? 'disabled' : (skill.eligible ? 'ready' : 'needs deps')}
                          </span>
                        </div>
                        <div className="text-[11px] text-white/50 truncate">{skill.description}</div>
                        {!skill.eligible && Array.isArray(skill.eligibility_issues) && skill.eligibility_issues.length > 0 && (
                          <div className="text-[11px] text-amber-200/90 mt-1 truncate">
                            {skill.eligibility_issues.join(', ')}
                          </div>
                        )}
                        {!skill.eligible && Array.isArray(skill.install_hints) && skill.install_hints.length > 0 && (
                          <div className="text-[11px] text-cyan-200/90 mt-1">
                            Install: {skill.install_hints.map((hint) => hint?.label || hint?.formula || hint?.id).filter(Boolean).join(', ')}
                          </div>
                        )}
                      </div>
                      <button
                        onClick={() => onUninstallSkill && onUninstallSkill(skill.name)}
                        disabled={skillsActionBusy || !skill.managed}
                        title={skill.managed ? 'Uninstall skill' : 'This skill is outside managed install root'}
                        className="px-2.5 py-1 rounded-md border border-red-400/20 text-red-300 text-xs hover:bg-red-400/10 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
                      >
                        <Trash2 size={12} />
                        Uninstall
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Memory */}
          <section className="space-y-4">
            <h3 className="text-sm font-medium text-white uppercase tracking-widest flex items-center gap-2">
              <Shield size={16} />
              {t('settings.memory')}
            </h3>
            
            <div className="bg-white/5 p-4 rounded-lg border border-white/10">
              <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-white/20 rounded-lg cursor-pointer hover:border-white/50 hover:bg-white/5 transition-all group">
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  <Upload className="w-8 h-8 mb-3 text-white/40 group-hover:text-white transition-colors" />
                  <p className="mb-2 text-sm text-white/60 group-hover:text-white/90">
                    <span className="font-semibold">{t('settings.import_memory')}</span>
                  </p>
                  <p className="text-xs text-white/40">TXT, MD, JSON</p>
                </div>
                <input
                  ref={memoryFileInputRef}
                  type="file"
                  className="hidden"
                  onChange={handleMemoryFiles}
                  accept=".txt,.md,.json"
                />
              </label>
            </div>
          </section>

        </div>
      </div>
    </div>
  );
};

export default SettingsWindow;
