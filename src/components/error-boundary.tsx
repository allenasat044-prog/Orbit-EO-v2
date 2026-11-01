import { Component, type ErrorInfo, type ReactNode } from "react";

// If one page crashes, show a message instead of a blank screen, and let people carry on.
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page crashed:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="dark grid min-h-screen place-items-center bg-[#0d1526] p-6 text-[#dbe4f7]">
        <div role="alert" className="max-w-md space-y-4 rounded-2xl border border-white/10 bg-white/[0.04] p-6 text-center">
          <h1 className="text-xl font-semibold text-white">Something went wrong on this page</h1>
          <p className="text-sm text-[#b0bed9]">The rest of Orbit EO is fine. Try the page again, or go back to the start.</p>
          <p className="break-words rounded-lg bg-black/30 p-2 font-mono text-xs text-red-300">{this.state.error.message}</p>
          <div className="flex justify-center gap-3">
            <button type="button" onClick={() => window.location.reload()} className="rounded-lg border border-white/15 px-4 py-2 text-sm hover:bg-white/5">Reload page</button>
            <a href="/" className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-black hover:opacity-90">Go home</a>
          </div>
        </div>
      </div>
    );
  }
}
