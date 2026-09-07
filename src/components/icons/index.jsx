import * as Phosphor from 'phosphor-react';

const fallback = () => () => null;
const from = (library, name) => library?.[name];
// Phosphor Regular is the single icon profile used by the shell. Keep aliases
// explicit for legacy component names so a missing glyph cannot silently pull
// in a second icon family with different proportions and stroke treatment.
const pick = (phosphorName) => from(Phosphor, phosphorName) || fallback();

export const X = pick('X');
export const Minus = pick('Minus');
export const Video = pick('VideoCamera');
export const Lock = pick('Lock');
export const Unlock = pick('LockOpen');
export const User = pick('User');
export const Heart = pick('Heart');
export const Utensils = pick('ForkKnife');
export const Gift = pick('Gift');
export const Smile = pick('Smiley');
export const Book = pick('Book');
export const ClipboardList = pick('ClipboardText');
export const Coffee = pick('Coffee');
export const Gamepad2 = pick('GameController');
export const Shield = pick('Shield');
export const Check = pick('Check');
export const Terminal = pick('TerminalWindow');
export const AlertTriangle = pick('Warning');
export const Bell = pick('Bell');
export const AlertCircle = pick('WarningCircle');
export const BookOpen = pick('BookOpen');
export const Send = pick('PaperPlaneRight');
export const RefreshCw = pick('ArrowsClockwise');
export const ChevronLeft = pick('CaretLeft');
export const ChevronRight = pick('CaretRight');
export const ChevronDown = pick('CaretDown');
export const ChevronUp = pick('CaretUp');
export const Upload = pick('ArrowUp');
export const Mic = pick('Microphone');
export const MicOff = pick('MicrophoneSlash');
export const Speaker = pick('SpeakerHigh');
export const Cpu = pick('Cpu');
export const Globe = pick('Globe');
export const Package = pick('Package');
export const Trash2 = pick('Trash');
export const Sparkles = pick('Sparkle');
export const HelpCircle = pick('Question');
export const Info = pick('Info');
export const PenTool = pick('Pencil');
export const Monitor = pick('Monitor');
export const CheckCircle = pick('CheckCircle');
export const Clock = pick('Clock');
export const Zap = pick('Lightning');
export const Edit2 = pick('PencilSimple');
export const Save = pick('FloppyDisk');
export const Activity = pick('Activity');
export const Moon = pick('Moon');
export const CheckSquare = pick('CheckSquare');
export const Folder = pick('Folder');
export const FileText = pick('FileText');
export const Loader2 = pick('Spinner');
export const Server = pick('Barricade');
export const Power = pick('Power');
export const Cake = pick('Cake');
export const Users = pick('Users');
export const Plus = pick('Plus');
export const Pin = pick('PushPin');
export const PinOff = pick('PushPinSlash');
export const XCircle = pick('XCircle');
export const ExternalLink = pick('ArrowSquareOut');
export const CloudSun = pick('CloudSun');
export const CloudRain = pick('CloudRain');
export const CloudSnow = pick('CloudSnow');
export const CloudLightning = pick('CloudLightning');
export const Sun = pick('Sun');
export const Cloud = pick('Cloud');
export const Calendar = pick('Calendar');
export const Newspaper = pick('Newspaper');
export const Brain = pick('Brain');
export const Maximize2 = pick('ArrowsOut');
export const Minimize2 = pick('ArrowsIn');
export const MessageSquare = pick('ChatCentered');
export const Paperclip = pick('Paperclip');
export const Settings = pick('Gear');
export const Bold = pick('TextBolder');
export const Eye = pick('Eye');
export const Highlighter = pick('HighlighterCircle');
export const Italic = pick('TextItalic');
export const List = pick('ListBullets');
export const ListOrdered = pick('ListNumbers');
export const BookOpenText = pick('BookOpen');
export const Flame = pick('Fire');
export const Gem = pick('Diamond');
export const MessageCircleHeart = pick('ChatTeardrop');
export const ScrollText = pick('Scroll');
export const Trophy = pick('Trophy');
export const Share2 = pick('ShareNetwork');
export const ZoomIn = pick('MagnifyingGlassPlus');
export const ZoomOut = pick('MagnifyingGlassMinus');
export const LogOut = pick('SignOut');
export const Leaf = pick('Leaf');
export const Search = pick('MagnifyingGlass');
export const Play = pick('Play');
export const CheckCircle2 = pick('CheckCircle');
export const Layers = pick('Stack');
export const ArrowRight = pick('ArrowRight');
export const Move = pick('ArrowsOutCardinal');

export default {
  X,
  Minus,
  Video,
  Lock,
  Unlock,
  User,
  Heart,
  Utensils,
  Gift,
  Smile,
  Book,
  ClipboardList,
  Coffee,
  Gamepad2,
  Shield,
  Check,
  Terminal,
  AlertTriangle,
  Bell,
  AlertCircle,
  BookOpen,
  Send,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Upload,
  Mic,
  MicOff,
  Speaker,
  Cpu,
  Globe,
  Package,
  Trash2,
  Sparkles,
  HelpCircle,
  Info,
  PenTool,
  Monitor,
  CheckCircle,
  Clock,
  Zap,
  Edit2,
  Save,
  Activity,
  Moon,
  CheckSquare,
  Folder,
  FileText,
  Loader2,
  Server,
  Power,
  Cake,
  Users,
  Plus,
  Pin,
  PinOff,
  XCircle,
  ExternalLink,
  CloudSun,
  CloudRain,
  CloudSnow,
  CloudLightning,
  Sun,
  Cloud,
  Calendar,
  Newspaper,
  Brain,
  Maximize2,
  Minimize2,
  MessageSquare,
  Paperclip,
  Settings,
  Bold,
  Eye,
  Highlighter,
  Italic,
  List,
  ListOrdered,
  BookOpenText,
  Flame,
  Gem,
  MessageCircleHeart,
  ScrollText,
  Trophy,
  Share2,
  ZoomIn,
  ZoomOut,
  LogOut,
  Leaf,
  Search,
  Play,
  CheckCircle2,
  Layers,
  ArrowRight,
  Move,
};
