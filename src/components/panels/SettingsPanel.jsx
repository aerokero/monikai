import React, { useRef, useState } from 'react';
import * as Icons from '../icons';
import { useLanguage } from '../../contexts/LanguageContext';
import { useMonika } from '../../contexts/MonikaContext';
import { useAudioVideo } from '../../contexts/AudioVideoContext';
import ShellPanelFrame from '../shared/ShellPanelFrame';

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

const SettingsRow = ({ title, description, children }) => (
  <div className="settings-row flex items-center justify-between py-3.5 border-b border-[#2c1e15] gap-4">
    <div className="flex flex-col min-w-0 flex-1">
      <span className="text-[13px] font-semibold text-[#f5e6d3] font-sans tracking-wide">{title}</span>
      {description && <span className="text-[11px] text-[#8c7769] font-sans mt-0.5 leading-relaxed">{description}</span>}
    </div>
    <div className="settings-row__control shrink-0 flex items-center justify-end">
      {children}
    </div>
  </div>
);

const Toggle = ({ checked, onChange }) => (
  <button
    onClick={() => onChange(!checked)}
    className={`w-11 h-6 rounded-full transition-colors relative flex items-center shrink-0 focus:outline-none ${
      checked ? 'bg-[#de9d50]' : 'bg-[#251c17]'
    }`}
  >
    <div className={`w-4 h-4 rounded-full transition-all duration-200 ${
      checked ? 'translate-x-[24px] bg-[#fff]' : 'translate-x-1 bg-[#5c4a3f]'
    }`} />
  </button>
);

const Dropdown = ({ value, onChange, options, className = "w-[220px] shrink-0" }) => (
  <div className={`settings-dropdown relative select-none ${className}`}>
    <select
      value={value}
      onChange={onChange}
      className="appearance-none bg-[#1e1612] text-[#f5e6d3] border border-[#3c2e26] rounded-[8px] pl-3 pr-8 py-2 text-xs focus:ring-0 focus:outline-none hover:border-[#de9d50] hover:text-[#de9d50] transition-colors cursor-pointer w-full truncate text-ellipsis"
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value} className="bg-[#140d08] text-[#f5e6d3]">
          {opt.label}
        </option>
      ))}
    </select>
    <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5 text-[#f5e6d3]/60">
      <Icons.ChevronDown size={11} />
    </div>
  </div>
);

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

  const renderSectionHeader = (title, isSensitive = false) => (
    <h3 className={`text-[10px] font-bold uppercase tracking-[0.22em] font-sans pt-5 pb-1 ${
      isSensitive ? 'text-[#a66a5e]' : 'text-[#806b5c]'
    }`}>
      {title}
    </h3>
  );

  return (
    <ShellPanelFrame
      icon={null}
      title={t('settings.title') || 'Settings'}
      subtitle=""
      titleClassName="font-serif text-[28px] text-[#f5e6d3] font-normal tracking-wide py-1"
      headerClassName="flex items-start justify-between gap-4 border-b border-[#2c1e15] bg-transparent px-6 pt-6 pb-4"
      bodyClassName="flex flex-col h-full overflow-hidden"
    >
      <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar text-sm pb-10">
        
        {/* PERSONALITY / JĘZYK I MODEL */}
        {renderSectionHeader(t('settings.language') + ' i model')}
        
        <SettingsRow title="Język aplikacji" description="Wybierz język interfejsu Moniki">
          <Dropdown
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            options={[
              { value: 'pl', label: 'Polski' },
              { value: 'en', label: 'English' },
              { value: 'zh', label: '中文' },
              { value: 'ja', label: '日本語' },
            ]}
          />
        </SettingsRow>

        <SettingsRow title="Preset modelu AI" description="Wybierz wersję modelu sztucznej inteligencji">
          <Dropdown
            value={geminiModelPreset}
            onChange={(e) => onModelPresetChange?.(e.target.value)}
            options={[
              { value: '2.5', label: 'Gemini 2.5 (Native Audio)' },
              { value: '3.1', label: 'Gemini 3.1 (Flash Live)' },
            ]}
          />
        </SettingsRow>

        <SettingsRow title="Głos" description="Wybierz głos lektora sztucznej inteligencji">
          <Dropdown
            value={geminiVoice}
            onChange={(e) => onVoiceChange?.(e.target.value)}
            options={GEMINI_VOICES}
          />
        </SettingsRow>

        {/* DEVICES / URZĄDZENIA */}
        {renderSectionHeader('Urządzenia')}

        <SettingsRow title="Mikrofon" description="Urządzenie wejściowe audio">
          <Dropdown
            value={selectedMicId}
            onChange={(e) => setSelectedMicId(e.target.value)}
            options={micDevices.map(device => ({
              value: device.deviceId,
              label: device.label || `Mikrofon ${device.deviceId.slice(0, 5)}...`
            }))}
          />
        </SettingsRow>

        <SettingsRow title="Głośnik" description="Urządzenie wyjściowe audio">
          <Dropdown
            value={selectedSpeakerId}
            onChange={(e) => setSelectedSpeakerId(e.target.value)}
            options={speakerDevices.map(device => ({
              value: device.deviceId,
              label: device.label || `Głośnik ${device.deviceId.slice(0, 5)}...`
            }))}
          />
        </SettingsRow>

        <SettingsRow title="Kamera" description="Urządzenie wideo">
          <Dropdown
            value={selectedWebcamId}
            onChange={(e) => setSelectedWebcamId(e.target.value)}
            options={webcamDevices.map(device => ({
              value: device.deviceId,
              label: device.label || `Kamera ${device.deviceId.slice(0, 5)}...`
            }))}
          />
        </SettingsRow>

        <SettingsRow title="Odbicie lustrzane kamery" description="Odwróć obraz wideo w poziomie">
          <Toggle checked={isCameraFlipped} onChange={setIsCameraFlipped} />
        </SettingsRow>

        {/* SECURITY / BEZPIECZEŃSTWO */}
        {renderSectionHeader(t('settings.security'), true)}

        {CONFIGURABLE_TOOLS.map((key) => {
          const val = toolPermissions[key] || false;
          return (
            <SettingsRow
              key={key}
              title={`Narzędzie: ${key.replace(/_/g, ' ')}`}
              description={`Zezwól modelowi na automatyczne uruchamianie funkcji ${key}`}
            >
              <Toggle checked={val} onChange={() => onTogglePermission && onTogglePermission(key)} />
            </SettingsRow>
          );
        })}

        {/* SKILLS / ROZSZERZENIA */}
        {renderSectionHeader('Rozszerzenia (Skills)')}

        <div className="border-b border-[#2c1e15] py-4 space-y-4">
          <div className="flex flex-col gap-2.5">
            <span className="text-[13px] font-semibold text-white/92">Zainstaluj nowe rozszerzenie</span>
            <div className="flex gap-2">
              <input
                value={skillSource}
                onChange={(e) => setSkillSource(e.target.value)}
                placeholder="Adres URL z repozytorium GitHub dla rozszerzenia"
                disabled={skillsActionBusy}
                className="flex-1 bg-white/5 border border-[#3c2e26] rounded-lg px-3 py-1.5 text-xs text-white placeholder-white/30 focus:border-white/30 focus:outline-none disabled:opacity-50"
              />
              <button
                onClick={submitSkillSource}
                disabled={skillsActionBusy || !skillSource.trim()}
                className="px-4 py-1.5 rounded-lg bg-[#de9d50] text-[#20160f] text-xs font-semibold hover:brightness-110 disabled:opacity-50 transition-all"
              >
                Instaluj
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input
                value={skillNameFilter}
                onChange={(e) => setSkillNameFilter(e.target.value)}
                placeholder="Nazwa rozszerzenia (opcjonalnie)"
                disabled={skillsActionBusy}
                className="bg-white/5 border border-[#3c2e26] rounded-lg px-3 py-1.5 text-xs text-white placeholder-white/30 focus:border-white/30 focus:outline-none disabled:opacity-50"
              />
              <Dropdown
                value={skillAgent}
                onChange={(e) => setSkillAgent(e.target.value)}
                className="w-full"
                options={[
                  { value: 'codex', label: 'Agent: Codex' },
                  { value: 'openclaw', label: 'Agent: OpenClaw' }
                ]}
              />
            </div>
            <label className="flex items-center gap-2 text-xs text-white/60 cursor-pointer">
              <input
                type="checkbox"
                checked={skillGlobalScope}
                onChange={(e) => setSkillGlobalScope(e.target.checked)}
                disabled={skillsActionBusy}
                className="accent-[#de9d50]"
              />
              Zainstaluj globalnie
            </label>
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
            className={`p-4 border border-dashed border-[#3c2e26] rounded-lg transition-all text-center ${
              isSkillDropActive
                ? 'border-[#de9d50] bg-white/5'
                : 'border-white/10 bg-black/10'
            }`}
          >
            <div className="flex flex-col items-center justify-center gap-2">
              <p className="text-[11px] text-white/50">Przeciągnij plik ZIP lub wybierz z komputera</p>
              <button
                onClick={() => skillFileInputRef.current?.click()}
                disabled={skillsActionBusy}
                className="px-3 py-1 rounded border border-white/10 text-[10px] text-white/80 hover:bg-white/5"
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
            <span className="text-[13px] font-semibold text-white/92">Zainstalowane rozszerzenia ({skills.length})</span>
            <button
              onClick={() => onRefreshSkills && onRefreshSkills()}
              disabled={skillsLoading || skillsActionBusy}
              className="p-1 rounded border border-white/10 text-white/60 hover:bg-white/5 disabled:opacity-50 flex items-center gap-1 text-[10px]"
            >
              <Icons.RefreshCw size={10} />
              Odśwież
            </button>
          </div>

          <div className="space-y-2 max-h-48 overflow-y-auto custom-scrollbar pr-1">
            {skillsLoading && <div className="text-[11px] text-white/50">Wczytywanie...</div>}
            {!skillsLoading && skills.length === 0 && <div className="text-[11px] text-white/30">Brak rozszerzeń.</div>}
            {!skillsLoading && skills.map((skill) => (
              <div key={`${skill.name}-${skill.path}`} className="flex items-center justify-between p-2 rounded-lg border border-white/5 bg-black/10 text-xs">
                <div className="min-w-0 pr-2">
                  <div className="font-semibold text-white/90 truncate flex items-center gap-1.5">
                    {skill.name}
                    <span className={`text-[8px] px-1 rounded-sm ${
                      skill.enabled === false
                        ? 'bg-red-500/10 text-red-300 border border-red-500/20'
                        : skill.eligible
                        ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20'
                        : 'bg-amber-500/10 text-amber-300 border border-amber-500/20'
                    }`}>
                      {skill.enabled === false ? 'wyłączone' : (skill.eligible ? 'gotowe' : 'wymaga zal.')}
                    </span>
                  </div>
                  <div className="text-[10px] text-white/40 truncate mt-0.5">{skill.description}</div>
                </div>
                <button
                  onClick={() => onUninstallSkill && onUninstallSkill(skill.name)}
                  disabled={skillsActionBusy || !skill.managed}
                  className="px-2 py-0.5 rounded border border-red-500/20 text-red-400 text-[10px] hover:bg-red-500/5 disabled:opacity-30"
                >
                  Usuń
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* MEMORY / PAMIĘĆ */}
        {renderSectionHeader(t('settings.memory'))}

        <div className="py-4">
          <label className="flex flex-col items-center justify-center w-full h-24 border border-dashed border-white/10 rounded-lg cursor-pointer hover:border-white/20 hover:bg-white/5 transition-all">
            <div className="flex flex-col items-center justify-center text-center px-4">
              <Icons.Upload className="w-5 h-5 mb-1.5 text-white/40" />
              <span className="text-xs text-white/60 font-semibold">{t('settings.import_memory')}</span>
              <span className="text-[10px] text-white/30 mt-0.5">TXT, MD, JSON</span>
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

        {/* BOTTOM BUTTONS / PRZYCISKI DOLNE */}
        <div className="flex gap-4 pt-8 pb-12 mt-4">
          <button
            onClick={onLogout}
            className="flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-full border border-[#3c2e26] bg-[#1e1612] text-[#f5e6d3] text-xs font-semibold hover:brightness-110 transition-all focus:outline-none"
          >
            <Icons.LogOut size={14} />
            Quit the App
          </button>
          <button
            onClick={() => setActiveContext('chat')}
            className="flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-full bg-[#de9d50] text-[#16100d] text-xs font-bold hover:brightness-110 transition-all shadow-[0_4px_16px_rgba(222,157,80,0.15)] focus:outline-none"
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
