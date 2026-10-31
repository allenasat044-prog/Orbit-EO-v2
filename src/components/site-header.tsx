import { Link, useLocation } from "react-router-dom";
import { BarChart3, BookMarked, Globe2, HelpCircle, Home, LayoutDashboard, MessageSquare, UserRound } from "lucide-react";

const links = [
  ["Home", "/", Home],
  ["Explore", "/explore", Globe2],
  ["Captions", "/captions", MessageSquare],
  ["Library", "/library", BookMarked],
  ["Analysis", "/analysis", BarChart3],
  ["Dashboard", "/dashboard", LayoutDashboard],
  ["FAQ", "/faqs", HelpCircle],
] as const;

// One shared header for every page, so the navigation always looks the same.
export default function SiteHeader() {
  const { pathname } = useLocation();
  const navLink = (on: boolean) =>
    `flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm transition-colors ${on ? "bg-white/10 text-white" : "text-[#b0bed9] hover:bg-white/5 hover:text-white"}`;
  return (
    <header className="border-b border-white/10 bg-black/40 backdrop-blur">
      <div className="mx-auto flex h-[72px] max-w-[1400px] items-center justify-between gap-4 px-6 sm:px-10">
        <Link to="/" className="flex shrink-0 items-center gap-3 text-lg font-medium text-[#f3f6ff]">
          <span className="grid size-9 place-items-center rounded-full bg-white text-black"><Globe2 className="size-5" /></span>
          Orbit EO
        </Link>
        <nav className="hidden items-center gap-1 lg:flex" aria-label="Main navigation">
          {links.map(([label, to, Icon]) => (
            <Link key={to} to={to} className={navLink(pathname === to)}>
              <Icon className="hidden size-4 2xl:block" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="flex shrink-0 items-center gap-2 text-sm">
          <Link
            to="/profile"
            aria-label="Profile"
            className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 transition-colors ${pathname === "/profile" ? "border-white/30 bg-white/10 text-white" : "border-white/15 text-[#dbe4f7] hover:bg-white/5 hover:text-white"}`}
          >
            <UserRound className="size-4" />
            <span className="hidden xl:inline">Profile</span>
          </Link>
          <Link to="/login" className="hidden px-2 text-[#b0bed9] hover:text-white xl:inline">Log in</Link>
          <Link to="/signup" className="rounded-lg bg-white px-3 py-1.5 font-medium text-black hover:opacity-90">Sign up</Link>
        </div>
      </div>
      {/* Smaller screens: the same links in a scrollable row */}
      <nav className="flex gap-1 overflow-x-auto px-4 pb-2 lg:hidden" aria-label="Main navigation (compact)">
        {links.map(([label, to, Icon]) => (
          <Link key={to} to={to} className={navLink(pathname === to)}>
            <Icon className="size-4" />
            {label}
          </Link>
        ))}
        <Link to="/profile" className={navLink(pathname === "/profile")}><UserRound className="size-4" />Profile</Link>
      </nav>
    </header>
  );
}
