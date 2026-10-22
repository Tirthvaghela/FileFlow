import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

// Default value (not null) so Header -- rendered standalone in most page
// tests, never wrapped in SidebarProvider there -- gets a harmless no-op
// toggle instead of a thrown error. The real app always renders Header
// inside DashboardLayout's own SidebarProvider, which overrides this.
const SidebarContext = createContext({ open: false, toggle: () => {}, close: () => {} });

// Below the lg breakpoint, Sidebar renders as an off-canvas drawer instead
// of the always-visible column -- this is the one piece of state Header's
// mobile menu button and Sidebar's own open/close both need to agree on.
export function SidebarProvider({ children }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // Picking a destination closes the drawer -- otherwise it stays open,
  // on top of the page you just navigated to.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  const toggle = useCallback(() => setOpen((v) => !v), []);
  const close = useCallback(() => setOpen(false), []);

  return (
    <SidebarContext.Provider value={{ open, toggle, close }}>{children}</SidebarContext.Provider>
  );
}

export function useSidebar() {
  return useContext(SidebarContext);
}
