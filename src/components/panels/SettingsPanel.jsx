import React, { useEffect, useRef, useState } from 'react';
import * as Icons from '../icons';
import { useLanguage } from '../../contexts/LanguageContext';
import { useMonika } from '../../contexts/MonikaContext';
import { useAudioVideo } from '../../contexts/AudioVideoContext';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import { SectionLabel, FieldRow, Toggle, SelectField, TextField, EmptyState, Badge, Checkbox, ListContainer, ListRow } from '../shared/panelPrimitives';

const GEMINI_VOICES = [
  { value: 'Leda',    label: 'Leda'    },
  { value: 'Aoede',   label: 'Aoede'   },
  { value: 'Kore',    label: 'Kore'    },
  { value: 'Sulafat', label: 'Sulafat' },
  { value: 'Puck',    label: 'Puck'    },
  { value: 'Charon',  label: 'Charon'  },
  { value: 'Fenrir',  label: 'Fenrir'  },
];

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

const skillStatus = (skill, t) => {
  if (skill.enabled === false) return { tone: 'red', label: t('settings.skill_status_disabled') };
  if (skill.eligible) return { tone: 'green', label: t('settings.skill_status_ready') };
  return { tone: 'amber', label: t('settings.skill_status_needs_deps') };
};

const SettingsPanel = ({
  micDevices = [],
  speakerDevices = [],
  webcamDevices = [],
  selectedMicId = '',
  setSelectedMicId = () => {},
  selectedSpeakerId = '',
  setSelectedSpeakerId = () => {},
  selectedWebcamId = '',
  setSelectedWebcamId = () => {},
  isCameraFlipped = false,
  setIsCameraFlipped = () => {},
  toolPermissions = {},
  onTogglePermission = () => {},
  handleFileUpload = () => {},
  skills = [],
  skillsLoading = false,
  skillsActionBusy = false,
  onRefreshSkills = () => {},
  onUploadSkillZip = () => {},
  onInstallSkillSource = () => {},
  onUninstallSkill = () => {},
  geminiModelPreset = '2.5',
  onModelPresetChange = () => {},
  geminiVoice = 'Leda',
  onVoiceChange = () => {},
  socket = null,
}) => {
  const { t, language, setLanguage } = useLanguage();
  const { setActiveContext } = useMonika();
  const { onLogout } = useAudioVideo();

  const [isSkillDropActive, setIsSkillDropActive] = useState(false);
  const [skillSource, setSkillSource] = useState('');
  const [skillNameFilter, setSkillNameFilter] = useState('');
  const [skillAgent, setSkillAgent] = useState('codex');
  const [skillGlobalScope, setSkillGlobalScope] = useState(false);

  const [modelsStatus, setModelsStatus] = useState(null);

  useEffect(() => {
    if (!socket) return;
    socket.emit('get_models');
    const onModelsStatus = (data) => {
      setModelsStatus(data);
    };
    socket.on('models_status', onModelsStatus);
    return () => {
      socket.off('models_status', onModelsStatus);
    };
  }, [socket]);

  const handleSelectModelProvider = (task, provider) => {
    if (!socket) return;
    socket.emit('select_model', { task, provider });
  };

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
    <ShellPanelFrame icon={Icons.Settings} title={t('settings.title') || 'Settings'}>
      <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar text-sm pb-10">

        <SectionLabel className="pt-2">{t('settings.language_and_model')}</SectionLabel>
        <FieldRow title={t('settings.language')} description={t('settings.language_desc')}>
          <SelectField
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            wrapperClassName="w-[220px]"
            options={[
              { value: 'pl', label: 'Polski' },
              { value: 'en', label: 'English' },
              { value: 'zh', label: '中文' },
              { value: 'ja', label: '日本語' },
            ]}
          />
        </FieldRow>
        <FieldRow title={t('settings.model_preset')} description={t('settings.model_preset_desc')}>
          <SelectField
            value={geminiModelPreset}
            onChange={(e) => onModelPresetChange?.(e.target.value)}
            wrapperClassName="w-[220px]"
            options={[
              { value: '2.5', label: 'Gemini 2.5 (Native Audio)' },
              { value: '3.1', label: 'Gemini 3.1 (Flash Live)' },
            ]}
          />
        </FieldRow>
        <FieldRow title={t('settings.voice')} description={t('settings.voice_desc')}>
          <SelectField
            value={geminiVoice}
            onChange={(e) => onVoiceChange?.(e.target.value)}
            wrapperClassName="w-[220px]"
            options={GEMINI_VOICES}
          />
        </FieldRow>

        <SectionLabel className="pt-6">Model Router (Odysseus Agent Hub)</SectionLabel>
        <FieldRow 
          title="Agent LLM Provider" 
          description="Model używany do zadań agenta, pisania i myślenia w tle"
        >
          <SelectField
            value={modelsStatus?.task_routing?.agent || modelsStatus?.default_provider || 'ollama'}
            onChange={(e) => handleSelectModelProvider('agent', e.target.value)}
            wrapperClassName="w-[220px]"
            options={[
              { value: 'ollama', label: 'Ollama (Local)' },
              { value: 'openrouter', label: 'OpenRouter (Claude/DeepSeek/GPT)' },
              { value: 'vllm', label: 'vLLM / llama.cpp (Local API)' },
            ]}
          />
        </FieldRow>
        <FieldRow 
          title="Deep Research LLM Provider" 
          description="Model dedykowany do wieloetapowego badania sieci i syntezy raportów"
        >
          <SelectField
            value={modelsStatus?.task_routing?.research || 'openrouter'}
            onChange={(e) => handleSelectModelProvider('research', e.target.value)}
            wrapperClassName="w-[220px]"
            options={[
              { value: 'openrouter', label: 'OpenRouter (Cloud)' },
              { value: 'ollama', label: 'Ollama (Local)' },
            ]}
          />
        </FieldRow>

        <SectionLabel className="pt-6">{t('settings.devices_section')}</SectionLabel>
        <FieldRow title={t('settings.microphone')} description={t('settings.microphone_desc')}>
          <SelectField
            value={selectedMicId}
            onChange={(e) => setSelectedMicId(e.target.value)}
            wrapperClassName="w-[220px]"
            options={micDevices.map(device => ({
              value: device.deviceId,
              label: device.label || t('settings.unnamed_microphone', { id: device.deviceId.slice(0, 5) })
            }))}
          />
        </FieldRow>
        <FieldRow title={t('settings.speaker')} description={t('settings.speaker_desc')}>
          <SelectField
            value={selectedSpeakerId}
            onChange={(e) => setSelectedSpeakerId(e.target.value)}
            wrapperClassName="w-[220px]"
            options={speakerDevices.map(device => ({
              value: device.deviceId,
              label: device.label || t('settings.unnamed_speaker', { id: device.deviceId.slice(0, 5) })
            }))}
          />
        </FieldRow>
        <FieldRow title={t('settings.camera')} description={t('settings.camera_desc')}>
          <SelectField
            value={selectedWebcamId}
            onChange={(e) => setSelectedWebcamId(e.target.value)}
            wrapperClassName="w-[220px]"
            options={webcamDevices.map(device => ({
              value: device.deviceId,
              label: device.label || t('settings.unnamed_camera', { id: device.deviceId.slice(0, 5) })
            }))}
          />
        </FieldRow>
        <FieldRow title={t('settings.mirror_vision')} description={t('settings.mirror_vision_desc')}>
          <Toggle checked={isCameraFlipped} onChange={setIsCameraFlipped} />
        </FieldRow>

        <SectionLabel className="pt-6">{t('settings.security')}</SectionLabel>
        {CONFIGURABLE_TOOLS.map((key) => {
          const val = toolPermissions[key] || false;
          return (
            <FieldRow
              key={key}
              title={t('settings.tool_label', { name: key.replace(/_/g, ' ') })}
              description={t('settings.tool_permission_desc', { name: key })}
            >
              <Toggle checked={val} onChange={() => onTogglePermission && onTogglePermission(key)} />
            </FieldRow>
          );
        })}

        <SectionLabel className="pt-6">{t('settings.skills_section')}</SectionLabel>
        <div className="border-b border-[#2c1e15] py-4 space-y-4">
          <div className="flex flex-col gap-2.5">
            <span className="text-[13px] font-semibold text-[#f5e6d3]">{t('settings.install_new_skill')}</span>
            <div className="flex gap-2">
              <TextField
                value={skillSource}
                onChange={(e) => setSkillSource(e.target.value)}
                placeholder={t('settings.skill_url_placeholder')}
                disabled={skillsActionBusy}
                size="sm"
                wrapperClassName="flex-1"
                className="disabled:opacity-50"
              />
              <button
                onClick={submitSkillSource}
                disabled={skillsActionBusy || !skillSource.trim()}
                className="shrink-0 rounded-lg bg-[#de9d50] px-4 py-1.5 text-xs font-semibold text-[#20160f] transition-all hover:brightness-110 disabled:opacity-50"
              >
                {t('settings.install')}
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <TextField
                value={skillNameFilter}
                onChange={(e) => setSkillNameFilter(e.target.value)}
                placeholder={t('settings.skill_name_placeholder')}
                disabled={skillsActionBusy}
                size="sm"
                className="disabled:opacity-50"
              />
              <SelectField
                value={skillAgent}
                onChange={(e) => setSkillAgent(e.target.value)}
                size="sm"
                options={[
                  { value: 'codex', label: t('settings.agent_codex') },
                  { value: 'openclaw', label: t('settings.agent_openclaw') }
                ]}
              />
            </div>
            <Checkbox
              checked={skillGlobalScope}
              onChange={setSkillGlobalScope}
              disabled={skillsActionBusy}
              label={t('settings.install_globally')}
            />
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
            className={`rounded-lg border border-dashed p-4 text-center transition-colors ${
              isSkillDropActive ? 'border-[#de9d50] bg-[#de9d50]/[0.06]' : 'border-[#3c2e26] bg-[#140d08]/40'
            }`}
          >
            <div className="flex flex-col items-center justify-center gap-2">
              <p className="text-[11px] text-[#8c7769]">{t('settings.skill_dropzone_hint')}</p>
              <button
                onClick={() => skillFileInputRef.current?.click()}
                disabled={skillsActionBusy}
                className="rounded border border-[#3c2e26] px-3 py-1 text-[10px] text-[#f5e6d3] hover:bg-white/5"
              >
                {t('settings.choose_file')}
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
        </div>

        <div className="py-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-semibold text-[#f5e6d3]">{t('settings.installed_skills', { count: skills.length })}</span>
            <button
              onClick={() => onRefreshSkills && onRefreshSkills()}
              disabled={skillsLoading || skillsActionBusy}
              className="flex items-center gap-1 rounded border border-[#3c2e26] p-1 text-[10px] text-[#8c7769] hover:bg-white/5 disabled:opacity-50"
            >
              <Icons.RefreshCw size={10} />
              {t('settings.refresh')}
            </button>
          </div>

          <div className="max-h-48 overflow-y-auto custom-scrollbar">
            {skillsLoading && <div className="text-[11px] text-[#8c7769]">{t('settings.loading')}</div>}
            {!skillsLoading && skills.length === 0 && <EmptyState>{t('settings.no_skills')}</EmptyState>}
            {!skillsLoading && skills.length > 0 && (
              <ListContainer>
                {skills.map((skill) => {
                  const status = skillStatus(skill, t);
                  return (
                    <ListRow
                      key={`${skill.name}-${skill.path}`}
                      className="py-2.5"
                      title={(
                        <span className="flex items-center gap-1.5 truncate font-semibold">
                          {skill.name}
                          <Badge tone={status.tone} className="normal-case tracking-normal">{status.label}</Badge>
                        </span>
                      )}
                      description={skill.description}
                      trailing={(
                        <button
                          onClick={() => onUninstallSkill && onUninstallSkill(skill.name)}
                          disabled={skillsActionBusy || !skill.managed}
                          className="shrink-0 rounded border border-[rgba(202,104,85,0.3)] px-2 py-0.5 text-[10px] text-[#df8978] hover:bg-[rgba(166,72,58,0.1)] disabled:opacity-30"
                        >
                          {t('settings.uninstall')}
                        </button>
                      )}
                    />
                  );
                })}
              </ListContainer>
            )}
          </div>
        </div>

        <SectionLabel className="pt-6">{t('settings.memory')}</SectionLabel>
        <div className="py-4">
          <label className="flex h-24 w-full cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-[#3c2e26] transition-colors hover:border-[#de9d50]/60 hover:bg-[#de9d50]/[0.04]">
            <div className="flex flex-col items-center justify-center px-4 text-center">
              <Icons.Upload className="mb-1.5 h-5 w-5 text-[#8c7769]" />
              <span className="text-xs font-semibold text-[#f5e6d3]">{t('settings.import_memory')}</span>
              <span className="mt-0.5 text-[10px] text-[#8c7769]">TXT, MD, JSON</span>
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

        <div className="mt-4 flex gap-4 pt-8 pb-12">
          <button
            onClick={onLogout}
            className="flex flex-1 items-center justify-center gap-2 rounded-full border border-[#3c2e26] bg-[#1e1612] px-4 py-3 text-xs font-semibold text-[#f5e6d3] transition-all hover:brightness-110 focus:outline-none"
          >
            <Icons.LogOut size={14} />
            {t('settings.quit_app')}
          </button>
          <button
            onClick={() => setActiveContext('chat')}
            className="flex flex-1 items-center justify-center gap-2 rounded-full bg-[#de9d50] px-4 py-3 text-xs font-bold text-[#16100d] shadow-[0_4px_16px_rgba(222,157,80,0.15)] transition-all hover:brightness-110 focus:outline-none"
          >
            <Icons.Check size={14} />
            {t('settings.save')}
          </button>
        </div>

      </div>
    </ShellPanelFrame>
  );
};

export default SettingsPanel;
