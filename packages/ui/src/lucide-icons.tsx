import type { LucideIcon, LucideProps } from "lucide-react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Banknote,
  Bell,
  Box,
  Calendar,
  CalendarDays,
  Car,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  CircleUser,
  ClipboardList,
  Clock,
  CreditCard,
  DollarSign,
  Download,
  Dumbbell,
  FileText,
  Filter,
  Gift,
  Heart,
  HeartPulse,
  Home,
  Image,
  Info,
  LayoutGrid,
  Loader2,
  Lock,
  LogOut,
  Mail,
  MapPin,
  Menu,
  MessageCircle,
  Minus,
  Package,
  PackageOpen,
  Phone,
  Plus,
  Receipt,
  RefreshCw,
  Search,
  Settings,
  Share2,
  Shield,
  ShieldCheck,
  ShoppingBag,
  ShoppingCart,
  Smartphone,
  Sofa,
  Sparkles,
  Star,
  Store,
  Tag,
  Ticket,
  Trash2,
  TrendingDown,
  TrendingUp,
  Truck,
  Upload,
  User,
  Users,
  Utensils,
  Wallet,
  Wrench,
  X,
  Zap,
  Shirt,
} from "lucide-react";

export type DuotoneLucideProps = LucideProps & {
  /** Tinted fill at ~20% alpha behind the stroke (icon tiles). */
  duotone?: boolean;
};

function withDuotone(Icon: LucideIcon) {
  return function DuotoneIcon({ duotone, className, ...props }: DuotoneLucideProps) {
    return (
      <Icon
        {...props}
        className={[
          className,
          duotone ? "fill-[color-mix(in_srgb,currentColor_20%,transparent)]" : undefined,
        ]
          .filter(Boolean)
          .join(" ")}
        strokeWidth={duotone ? 1.75 : (props.strokeWidth ?? 2)}
      />
    );
  };
}

export const LcHome = withDuotone(Home);
export const LcSearch = withDuotone(Search);
export const LcShoppingCart = withDuotone(ShoppingCart);
export const LcShoppingBag = withDuotone(ShoppingBag);
export const LcPackage = withDuotone(Package);
export const LcPackageOpen = withDuotone(PackageOpen);
export const LcTruck = withDuotone(Truck);
export const LcMapPin = withDuotone(MapPin);
export const LcStore = withDuotone(Store);
export const LcUser = withDuotone(User);
export const LcUsers = withDuotone(Users);
export const LcSettings = withDuotone(Settings);
export const LcBell = withDuotone(Bell);
export const LcHeart = withDuotone(Heart);
export const LcStar = withDuotone(Star);
export const LcCalendar = withDuotone(Calendar);
export const LcCalendarDays = withDuotone(CalendarDays);
export const LcTicket = withDuotone(Ticket);
export const LcWrench = withDuotone(Wrench);
export const LcBanknote = withDuotone(Banknote);
export const LcWallet = withDuotone(Wallet);
export const LcCreditCard = withDuotone(CreditCard);
export const LcDollarSign = withDuotone(DollarSign);
export const LcReceipt = withDuotone(Receipt);
export const LcShield = withDuotone(Shield);
export const LcShieldCheck = withDuotone(ShieldCheck);
export const LcBadgeCheck = withDuotone(BadgeCheck);
export const LcCheck = withDuotone(Check);
export const LcCheckCircle2 = withDuotone(CheckCircle2);
export const LcAlertCircle = withDuotone(AlertCircle);
export const LcAlertTriangle = withDuotone(AlertTriangle);
export const LcInfo = withDuotone(Info);
export const LcCircleHelp = withDuotone(CircleHelp);
export const LcLoader2 = withDuotone(Loader2);
export const LcFilter = withDuotone(Filter);
export const LcLayoutGrid = withDuotone(LayoutGrid);
export const LcMenu = withDuotone(Menu);
export const LcChevronDown = withDuotone(ChevronDown);
export const LcChevronLeft = withDuotone(ChevronLeft);
export const LcChevronRight = withDuotone(ChevronRight);
export const LcArrowLeft = withDuotone(ArrowLeft);
export const LcArrowRight = withDuotone(ArrowRight);
export const LcPlus = withDuotone(Plus);
export const LcMinus = withDuotone(Minus);
export const LcX = withDuotone(X);
export const LcShare2 = withDuotone(Share2);
export const LcUpload = withDuotone(Upload);
export const LcDownload = withDuotone(Download);
export const LcRefreshCw = withDuotone(RefreshCw);
export const LcTrash2 = withDuotone(Trash2);
export const LcMail = withDuotone(Mail);
export const LcPhone = withDuotone(Phone);
export const LcMessageCircle = withDuotone(MessageCircle);
export const LcImage = withDuotone(Image);
export const LcFileText = withDuotone(FileText);
export const LcClipboardList = withDuotone(ClipboardList);
export const LcClock = withDuotone(Clock);
export const LcLock = withDuotone(Lock);
export const LcLogOut = withDuotone(LogOut);
export const LcGift = withDuotone(Gift);
export const LcTag = withDuotone(Tag);
export const LcTrendingUp = withDuotone(TrendingUp);
export const LcTrendingDown = withDuotone(TrendingDown);
export const LcZap = withDuotone(Zap);
export const LcSparkles = withDuotone(Sparkles);
export const LcHeartPulse = withDuotone(HeartPulse);
export const LcUtensils = withDuotone(Utensils);
export const LcDumbbell = withDuotone(Dumbbell);
export const LcSofa = withDuotone(Sofa);
export const LcCar = withDuotone(Car);
export const LcSmartphone = withDuotone(Smartphone);
export const LcShirt = withDuotone(Shirt);
export const LcCircleUser = withDuotone(CircleUser);
export const LcBox = withDuotone(Box);

/** Curated Lucide set for tree-shaken commerce/dashboard UI (~60 icons). */
export const LUCIDE_ICON_NAMES = [
  "home",
  "search",
  "shopping-cart",
  "package",
  "truck",
  "map-pin",
  "store",
  "user",
  "settings",
  "banknote",
  "wallet",
  "calendar",
  "wrench",
  "shield-check",
  "sparkles",
  "layout-grid",
] as const;
