import React, { useRef, useState } from 'react';
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

const skillStatus = (skill) => {
  if (skill.enabled === false) return { tone: 'red', label: 'wyłączone' };
  if (skill.eligible) return { tone: 'green', label: 'gotowe' };
  return { tone: 'amber', label: 'wymaga zal.' };
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
}) => {
  const { t, language, setLanguage } = useLanguage();
  const { setActiveContext } = useMonika();
  const { onLogout } = useAudioVideo();

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
    <ShellPanelFrame icon={Icons.Settings} title={t('settings.title') || 'Settings'}>
      <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar text-sm pb-10">

        <SectionLabel className="pt-2">{t('settings.language')} i model</SectionLabel>
        <FieldRow title="Język aplikacji" description="Wybierz język interfejsu Moniki">
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
        <FieldRow title="Preset modelu AI" description="Wybierz wersję modelu sztucznej inteligencji">
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
        <FieldRow title="Głos" description="Wybierz głos lektora sztucznej inteligencji">
          <SelectField
            value={geminiVoice}
            onChange={(e) => onVoiceChange?.(e.target.value)}
            wrapperClassName="w-[220px]"
            options={GEMINI_VOICES}
          />
        </FieldRow>

        <SectionLabel className="pt-6">Urządzenia</SectionLabel>
        <FieldRow title="Mikrofon" description="Urządzenie wejściowe audio">
          <SelectField
            value={selectedMicId}
            onChange={(e) => setSelectedMicId(e.target.value)}
            wrapperClassName="w-[220px]"
            options={micDevices.map(device => ({
              value: device.deviceId,
              label: device.label || `Mikrofon ${device.deviceId.slice(0, 5)}...`
            }))}
          />
        </FieldRow>
        <FieldRow title="Głośnik" description="Urządzenie wyjściowe audio">
          <SelectField
            value={selectedSpeakerId}
            onChange={(e) => setSelectedSpeakerId(e.target.value)}
            wrapperClassName="w-[220px]"
            options={speakerDevices.map(device => ({
              value: device.deviceId,
              label: device.label || `Głośnik ${device.deviceId.slice(0, 5)}...`
            }))}
          />
        </FieldRow>
        <FieldRow title="Kamera" description="Urządzenie wideo">
          <SelectField
            value={selectedWebcamId}
            onChange={(e) => setSelectedWebcamId(e.target.value)}
            wrapperClassName="w-[220px]"
            options={webcamDevices.map(device => ({
              value: device.deviceId,
              label: device.label || `Kamera ${device.deviceId.slice(0, 5)}...`
            }))}
          />
        </FieldRow>
        <FieldRow title="Odbicie lustrzane kamery" description="Odwróć obraz wideo w poziomie">
          <Toggle checked={isCameraFlipped} onChange={setIsCameraFlipped} />
        </FieldRow>

        <SectionLabel className="pt-6">{t('settings.security')}</SectionLabel>
        {CONFIGURABLE_TOOLS.map((key) => {
          const val = toolPermissions[key] || false;
          return (
            <FieldRow
              key={key}
              title={`Narzędzie: ${key.replace(/_/g, ' ')}`}
              description={`Zezwól modelowi na automatyczne uruchamianie funkcji ${key}`}
            >
              <Toggle checked={val} onChange={() => onTogglePermission && onTogglePermission(key)} />
            </FieldRow>
          );
        })}

        <SectionLabel className="pt-6">Rozszerzenia (Skills)</SectionLabel>
        <div className="border-b border-[#2c1e15] py-4 space-y-4">
          <div className="flex flex-col gap-2.5">
            <span className="text-[13px] font-semibold text-[#f5e6d3]">Zainstaluj nowe rozszerzenie</span>
            <div className="flex gap-2">
              <TextField
                value={skillSource}
                onChange={(e) => setSkillSource(e.target.value)}
                placeholder="Adres URL z repozytorium GitHub dla rozszerzenia"
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
                Instaluj
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <TextField
                value={skillNameFilter}
                onChange={(e) => setSkillNameFilter(e.target.value)}
                placeholder="Nazwa rozszerzenia (opcjonalnie)"
                disabled={skillsActionBusy}
                size="sm"
                className="disabled:opacity-50"
              />
              <SelectField
                value={skillAgent}
                onChange={(e) => setSkillAgent(e.target.value)}
                size="sm"
                options={[
                  { value: 'codex', label: 'Agent: Codex' },
                  { value: 'openclaw', label: 'Agent: OpenClaw' }
                ]}
              />
            </div>
            <Checkbox
              checked={skillGlobalScope}
              onChange={setSkillGlobalScope}
              disabled={skillsActionBusy}
              label="Zainstaluj globalnie"
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
              <p className="text-[11px] text-[#8c7769]">Przeciągnij plik ZIP lub wybierz z komputera</p>
              <button
                onClick={() => skillFileInputRef.current?.click()}
                disabled={skillsActionBusy}
                className="rounded border border-[#3c2e26] px-3 py-1 text-[10px] text-[#f5e6d3] hover:bg-white/5"
              >
                Wybierz plik
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
            <span className="text-[13px] font-semibold text-[#f5e6d3]">Zainstalowane rozszerzenia ({skills.length})</span>
            <button
              onClick={() => onRefreshSkills && onRefreshSkills()}
              disabled={skillsLoading || skillsActionBusy}
              className="flex items-center gap-1 rounded border border-[#3c2e26] p-1 text-[10px] text-[#8c7769] hover:bg-white/5 disabled:opacity-50"
            >
              <Icons.RefreshCw size={10} />
              Odśwież
            </button>
          </div>

          <div className="max-h-48 overflow-y-auto custom-scrollbar">
            {skillsLoading && <div className="text-[11px] text-[#8c7769]">Wczytywanie...</div>}
            {!skillsLoading && skills.length === 0 && <EmptyState>Brak rozszerzeń.</EmptyState>}
            {!skillsLoading && skills.length > 0 && (
              <ListContainer>
                {skills.map((skill) => {
                  const status = skillStatus(skill);
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
                          Usuń
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
            Quit the App
          </button>
          <button
            onClick={() => setActiveContext('chat')}
            className="flex flex-1 items-center justify-center gap-2 rounded-full bg-[#de9d50] px-4 py-3 text-xs font-bold text-[#16100d] shadow-[0_4px_16px_rgba(222,157,80,0.15)] transition-all hover:brightness-110 focus:outline-none"
          >
            <Icons.Check size={14} />
            Save
          </button>
        </div>

      </div>
    </ShellPanelFrame>
  );
};

export default SettingsPanel;
