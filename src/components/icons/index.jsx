import * as Phosphor from 'phosphor-react';
import * as Lucide from 'lucide-react';

const fallback = () => () => null;
const from = (library, name) => library?.[name];
const pick = (phosphorName, lucideName = phosphorName) => from(Phosphor, phosphorName) || from(Lucide, lucideName) || fallback();

export const X = pick('X');
export const Minus = pick('Minus');
export const Video = pick('CameraVideo', 'Video');
export const Lock = pick('Lock');
export const Unlock = pick('LockOpen', 'Unlock');
export const User = pick('User');
export const Heart = pick('Heart');
export const Utensils = pick('ForkKnife', 'Utensils');
export const Gift = pick('Gift');
export const Smile = pick('Smiley', 'Smile');
export const Book = pick('Book');
export const ClipboardList = pick('ClipboardText', 'ClipboardList');
export const Coffee = pick('Coffee');
export const Gamepad2 = pick('GameController', 'Gamepad2');
export const Shield = pick('Shield');
export const Check = pick('Check');
export const Terminal = pick('TerminalWindow', 'Terminal');
export const AlertTriangle = pick('Warning', 'AlertTriangle');
export const Bell = pick('Bell');
export const AlertCircle = pick('WarningCircle', 'AlertCircle');
export const BookOpen = pick('BookOpen');
export const Send = pick('PaperPlaneRight', 'Send');
export const RefreshCw = pick('ArrowsClockwise', 'RefreshCw');
export const ChevronLeft = pick('CaretLeft', 'ChevronLeft');
export const ChevronRight = pick('CaretRight', 'ChevronRight');
export const ChevronDown = pick('CaretDown', 'ChevronDown');
export const ChevronUp = pick('CaretUp', 'ChevronUp');
export const Upload = pick('ArrowUp', 'Upload');
export const Mic = pick('Microphone', 'Mic');
export const Speaker = pick('SpeakerHigh', 'Speaker');
export const Cpu = pick('Cpu', 'Cpu');
export const Globe = pick('Globe', 'Globe');
export const Package = pick('Package', 'Package');
export const Trash2 = pick('Trash', 'Trash2');
export const Sparkles = pick('Sparkle', 'Sparkles');
export const HelpCircle = pick('Question', 'HelpCircle');
export const Info = pick('Info');
export const PenTool = pick('Pencil', 'PenTool');
export const Monitor = pick('Monitor', 'Monitor');
export const CheckCircle = pick('CircleCheck', 'CheckCircle');
export const Clock = pick('Clock');
export const Zap = pick('Lightning', 'Zap');
export const Edit2 = pick('PencilSimple', 'Edit2');
export const Save = pick('FloppyDisk', 'Save');
export const Activity = pick('Activity');
export const Moon = pick('Moon');
export const CheckSquare = pick('CheckSquare');
export const Folder = pick('Folder');
export const FileText = pick('FileText');
export const Loader2 = pick('Spinner', 'Loader2');
export const Server = pick('Barricade', 'Server');
export const Power = pick('Power');
export const Cake = pick('Cake');
export const Users = pick('Users');
export const Plus = pick('Plus');
export const Pin = pick('PushPin', 'Pin');
export const PinOff = pick('PushPinSlash', 'PinOff');
export const XCircle = pick('XCircle');
export const ExternalLink = pick('ArrowSquareOut', 'ExternalLink');
export const CloudSun = pick('CloudSun', 'CloudSun');
export const CloudRain = pick('CloudRain', 'CloudRain');
export const CloudSnow = pick('CloudSnow', 'CloudSnow');
export const CloudLightning = pick('CloudLightning', 'CloudLightning');
export const Sun = pick('Sun', 'Sun');
export const Cloud = pick('Cloud', 'Cloud');
export const Calendar = pick('Calendar', 'Calendar');
export const Newspaper = pick('Newspaper', 'Newspaper');
export const Brain = pick('Brain', 'Brain');
export const Maximize2 = pick('ArrowsOut', 'Maximize2');
export const MessageSquare = pick('ChatCentered', 'MessageSquare');
export const Paperclip = pick('Paperclip', 'Paperclip');
export const Settings = pick('Gear', 'Settings');
export const Bold = pick('TextB', 'Bold');
export const Eye = pick('Eye');
export const Highlighter = pick('HighlighterCircle', 'Highlighter');
export const Italic = pick('TextItalic', 'Italic');
export const List = pick('ListBullets', 'List');
export const ListOrdered = pick('ListNumbers', 'ListOrdered');
export const BookOpenText = pick('BookOpenText', 'BookOpenText');
export const Flame = pick('Fire', 'Flame');
export const Gem = pick('Diamond', 'Gem');
export const MessageCircleHeart = pick('ChatTeardropHeart', 'MessageCircleHeart');
export const ScrollText = pick('Scroll', 'ScrollText');
export const Trophy = pick('Trophy', 'Trophy');
export const Share2 = pick('ShareNetwork', 'Share2');
export const ZoomIn = pick('MagnifyingGlassPlus', 'ZoomIn');
export const ZoomOut = pick('MagnifyingGlassMinus', 'ZoomOut');
export const LogOut = pick('SignOut', 'LogOut');

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
};
