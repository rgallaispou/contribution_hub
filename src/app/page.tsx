"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowDownLeft, ArrowDownUp, ArrowUpRight, Bell, BookOpen,
  Check, CircleDot, Clock3, ExternalLink, FileUp, Inbox,
  LayoutDashboard, ListChecks, LoaderCircle, MessageSquareText,
  RefreshCw, Search, Settings2, X,
} from "lucide-react";

type IdentityStats = {
  email: string;
  patch_series: number;
  messages_sent: number;
  review_trailers_in_own_threads: number;
  reply_suggestions_in_own_threads: number;
};

type Overview = {
  identities: IdentityStats[];
  combined: {
    unique_patch_series: number;
    unique_messages: number;
    reply_suggestions: number;
  };
};

type Contribution = {
  id: number;
  subject: string;
  project: string | null;
  identities: string[];
  message_count: number;
  last_activity: string | null;
  lore_url: string | null;
};

type ReplyTask = {
  id: number;
  message_id: string;
  subject: string;
  sender: string;
  reason: string;
  confidence: "low" | "medium" | "high";
  status: "suggested" | "done" | "dismissed";
  lore_url: string;
};

type View = "all" | "outgoing" | "incoming";

function displayDate(value: string | null) {
  if (!value) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

export default function Dashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [contributions, setContributions] = useState<Contribution[]>([]);
  const [replyTasks, setReplyTasks] = useState<ReplyTask[]>([]);
  const [selectedIdentity, setSelectedIdentity] = useState("");
  const [view, setView] = useState<View>("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [syncingLore, setSyncingLore] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState<number | null>(null);
  const [toast, setToast] = useState("");

  useEffect(() => {
    let active = true;
    async function loadDashboard() {
      setLoading(true);
      setError("");
      try {
        const responses = await Promise.all([
          fetch("/api/dashboard/overview", { cache: "no-store" }),
          fetch("/api/contributions?limit=500", { cache: "no-store" }),
          fetch("/api/reply-tasks", { cache: "no-store" }),
        ]);
        const failed = responses.find((response) => !response.ok);
        if (failed) throw new Error(`API request failed (${failed.status})`);
        const [nextOverview, nextContributions, nextTasks] = await Promise.all(responses.map((response) => response.json()));
        if (!active) return;
        const parsedOverview = nextOverview as Overview;
        setOverview(parsedOverview);
        setContributions(nextContributions as Contribution[]);
        setReplyTasks(nextTasks as ReplyTask[]);
        setSelectedIdentity((current) => parsedOverview.identities.some((identity) => identity.email === current)
          ? current
          : parsedOverview.identities[0]?.email ?? "");
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load dashboard data");
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadDashboard();
    return () => { active = false; };
  }, [refreshKey]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const currentStats = overview?.identities.find((identity) => identity.email === selectedIdentity);
  const matchesIdentity = (item: Contribution) => selectedIdentity !== "" && item.identities.includes(selectedIdentity);
  const filteredContributions = contributions.filter((item) => {
    const ownSeries = matchesIdentity(item);
    const directionMatches = view === "all" || (view === "outgoing" ? ownSeries : !ownSeries);
    const needle = query.trim().toLowerCase();
    return directionMatches && (!needle || `${item.subject} ${item.project ?? ""} ${item.identities.join(" ")}`.toLowerCase().includes(needle));
  });
  const openTasks = replyTasks.filter((task) => task.status === "suggested");

  async function updateTask(taskId: number, status: ReplyTask["status"]) {
    setBusyTaskId(taskId);
    try {
      const response = await fetch(`/api/reply-tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) throw new Error(`Could not update task (${response.status})`);
      setReplyTasks((current) => current.map((task) => task.id === taskId ? { ...task, status } : task));
      setToast(status === "done" ? "Reply suggestion marked done" : "Reply suggestion dismissed");
    } catch (cause) {
      setToast(cause instanceof Error ? cause.message : "Could not update reply suggestion");
    } finally {
      setBusyTaskId(null);
    }
  }

  async function importMbox(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const path = String(form.get("path") ?? "").trim();
    if (!path) return;
    try {
      const response = await fetch(`/api/import/mbox?path=${encodeURIComponent(path)}`, { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? `Import failed (${response.status})`);
      setModalOpen(false);
      setToast(`Imported ${result.imported}; skipped ${result.skipped_duplicates_or_missing_id}`);
      setRefreshKey((current) => current + 1);
    } catch (cause) {
      setToast(cause instanceof Error ? cause.message : "Import failed");
    }
  }

  async function syncLore() {
    setSyncingLore(true);
    try {
      const response = await fetch("/api/lore/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_threads: 10 }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? `Lore sync failed (${response.status})`);
      setToast(`Lore sync: ${result.threads_fetched} threads, ${result.messages_imported} new messages`);
      setRefreshKey((current) => current + 1);
    } catch (cause) {
      setToast(cause instanceof Error ? cause.message : "Could not sync Lore");
    } finally {
      setSyncingLore(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><ArrowDownUp size={18} strokeWidth={2.3} /></div>
          <div><div className="brand-name">patchwork</div><div className="brand-caption">CONTRIBUTION HUB</div></div>
        </div>
        <div className="nav-label">Workspace</div>
        <nav className="nav-list" aria-label="Main navigation">
          <button className="nav-item active"><LayoutDashboard size={16} /> Overview</button>
          <button className={`nav-item ${view === "incoming" ? "active" : ""}`} onClick={() => setView("incoming")}><Inbox size={16} /> Other authors <span className="nav-count">{contributions.filter((item) => !matchesIdentity(item)).length}</span></button>
          <button className={`nav-item ${view === "outgoing" ? "active" : ""}`} onClick={() => setView("outgoing")}><ArrowUpRight size={16} /> Your patch series <span className="nav-count">{currentStats?.patch_series ?? 0}</span></button>
          <button className="nav-item" onClick={() => document.getElementById("reply-tasks")?.scrollIntoView({ behavior: "smooth" })}><ListChecks size={16} /> Reply suggestions <span className="nav-count">{openTasks.length}</span></button>
        </nav>
        <div className="nav-label" style={{ marginTop: 27 }}>Identity</div>
        <label className="nav-item" style={{ paddingRight: 7 }}><CircleDot size={15} /><select aria-label="Select email identity" value={selectedIdentity} onChange={(event) => setSelectedIdentity(event.target.value)} style={{ minWidth: 0, width: "100%", border: 0, background: "transparent", color: "inherit", outline: "none", fontSize: 11 }}>{overview?.identities.map((identity) => <option key={identity.email} value={identity.email} style={{ color: "#1d2822" }}>{identity.email}</option>)}</select></label>
        <div className="sidebar-bottom">
          <div className="nav-label">Archive</div>
          <button className="nav-item" onClick={() => setModalOpen(true)}><BookOpen size={16} /> Import mbox</button>
          <div className="profile"><div className="avatar">{selectedIdentity.slice(0, 2).toUpperCase() || "CH"}</div><div style={{ minWidth: 0 }}><div className="profile-name">Selected identity</div><div className="profile-handle" title={selectedIdentity}>{selectedIdentity || "No identities configured"}</div></div><Settings2 size={16} style={{ marginLeft: "auto", color: "#9daaa1", flex: "0 0 auto" }} /></div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="crumb">Workspace <span style={{ padding: "0 7px", color: "#b0b9b1" }}>/</span> <strong>Overview</strong></div>
          <div className="top-actions"><div className="demo-label"><span className="demo-dot" style={{ background: error ? "#b95d32" : "#4e9a68" }} /> SELF-HOSTED ARCHIVE</div><button className="icon-button" aria-label="Refresh dashboard" onClick={() => setRefreshKey((current) => current + 1)}><RefreshCw size={15} /></button><button className="icon-button" aria-label="Reply suggestions" onClick={() => document.getElementById("reply-tasks")?.scrollIntoView({ behavior: "smooth" })}><Bell size={15} /></button></div>
        </header>

        <div className="page-content">
          <div className="page-heading">
            <div><div className="eyebrow">PRIVATE MAILING-LIST WORKSPACE</div><h1>Your contribution queue</h1><p className="heading-subtitle">Patch threads and possible reply tasks from Lore and imported mail.</p></div>
            <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "flex-end", gap: 8 }}><button className="secondary-button" onClick={() => void syncLore()} disabled={syncingLore} title="Search Lore for messages sent to or from your configured identities">{syncingLore ? <LoaderCircle size={14} className="spin" /> : <RefreshCw size={14} />} {syncingLore ? "Syncing Lore" : "Sync Lore"}</button><button className="primary-button heading-action" onClick={() => setModalOpen(true)}><FileUp size={15} /> Import mbox</button></div>
          </div>

          {error && <div role="alert" className="lower-panel" style={{ marginBottom: 18, borderColor: "#e4b7aa", color: "#874d3b" }}>API unavailable: {error}. Start the backend and refresh this dashboard.</div>}

          <section className="metrics" aria-label="Contribution summary">
            <article className="metric"><div className="metric-label">Patch series in archive</div><div className="metric-value">{loading ? "--" : overview?.combined.unique_patch_series ?? 0}</div><div className="metric-foot">Grouped conservatively by normalized subject</div></article>
            <article className="metric"><div className="metric-label">Messages imported</div><div className="metric-value">{loading ? "--" : overview?.combined.unique_messages ?? 0}</div><div className="metric-foot">Unique Message-IDs in the local database</div></article>
            <article className="metric"><div className="metric-label">Reply suggestions</div><div className="metric-value">{loading ? "--" : openTasks.length}</div><div className="metric-foot">Heuristic prompts for your review, not facts</div></article>
            <article className="metric"><div className="metric-label">Your patch series</div><div className="metric-value">{loading ? "--" : currentStats?.patch_series ?? 0}</div><div className="metric-foot">For the selected email identity</div></article>
          </section>

          <div className="section-head"><h2 className="section-title">Patch series</h2><span className="section-note">Lore search and imported archives · status is not inferred as accepted/applied.</span></div>
          <section className="tracker" aria-label="Patch series">
            <div className="tracker-toolbar">
              <div className="tabs" role="tablist" aria-label="Contribution direction">
                <button role="tab" aria-selected={view === "all"} className={`tab ${view === "all" ? "selected" : ""}`} onClick={() => setView("all")}><ArrowDownUp size={14} /> All series</button>
                <button role="tab" aria-selected={view === "outgoing"} className={`tab ${view === "outgoing" ? "selected" : ""}`} onClick={() => setView("outgoing")}><ArrowUpRight size={14} /> From my identity</button>
                <button role="tab" aria-selected={view === "incoming"} className={`tab ${view === "incoming" ? "selected" : ""}`} onClick={() => setView("incoming")}><ArrowDownLeft size={14} /> Other authors</button>
              </div>
              <div className="filters"><label className="search-wrap"><Search className="search-icon" size={14} /><input className="search-input" aria-label="Search patch series" placeholder="Search subject or project..." value={query} onChange={(event) => setQuery(event.target.value)} /></label></div>
            </div>
            <div className="table-scroll">
              <table className="contribution-table">
                <thead><tr><th>Patch series</th><th>Attribution</th><th>Messages</th><th>Last activity</th><th>Thread</th></tr></thead>
                <tbody>
                  {filteredContributions.map((item) => {
                    const ownSeries = matchesIdentity(item);
                    return <tr key={item.id} className="contribution-row">
                      <td><div className="patch-title">{item.subject}</div><div className="patch-meta">{item.project || "Project not identified"} <span style={{ color: "#c2c9c2" }}>·</span> series #{item.id}</div></td>
                      <td><span className={`status ${ownSeries ? "status-sent" : "status-review"}`}>{ownSeries ? "Your identity" : "Other author"}</span></td>
                      <td><span className="date-text"><MessageSquareText size={11} style={{ display: "inline", verticalAlign: "-2px" }} /> {item.message_count}</span></td>
                      <td><span className="date-text"><Clock3 size={11} style={{ display: "inline", verticalAlign: "-2px" }} /> {displayDate(item.last_activity)}</span></td>
                      <td>{item.lore_url ? <a className="selected-link" href={item.lore_url} target="_blank" rel="noreferrer" aria-label={`Open lore thread for ${item.subject}`}><ExternalLink size={14} /></a> : <span className="section-note">Unavailable</span>}</td>
                    </tr>;
                  })}
                  {!loading && filteredContributions.length === 0 && <tr><td colSpan={5}><div className="empty-state">{error ? "Waiting for the API connection." : "No matching patch series found on Lore or in imported archives."}</div></td></tr>}
                  {loading && <tr><td colSpan={5}><div className="empty-state"><LoaderCircle size={16} style={{ display: "inline", verticalAlign: "-3px", marginRight: 7 }} />Loading archive data...</div></td></tr>}
                </tbody>
              </table>
            </div>
            <div className="table-footer"><span>Showing <strong>{filteredContributions.length}</strong> of <strong>{contributions.length}</strong> series</span><span>Source: Lore search and imported mbox</span></div>
          </section>

          <section className="lower-panel" id="reply-tasks" style={{ marginTop: 20 }}>
            <div className="activity-head"><div><h2 className="section-title">Reply suggestions</h2><div className="section-note" style={{ marginTop: 5 }}>Language-based heuristics. Review the thread before acting.</div></div><span className="tab-count">{openTasks.length} open</span></div>
            {openTasks.length === 0 ? <div className="selected-empty">No open suggestions. Sync Lore or import more mailbox messages to update this list.</div> : <div style={{ display: "grid", gap: 0, marginTop: 9 }}>
              {openTasks.map((task) => <article key={task.id} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 16, alignItems: "center", padding: "13px 0", borderTop: "1px solid #edf0eb" }}>
                <div style={{ minWidth: 0 }}><div className="patch-title">{task.subject}</div><div className="patch-meta">From {task.sender} · {task.confidence} confidence · {task.reason}</div><a className="selected-link" href={task.lore_url} target="_blank" rel="noreferrer">Open message <ExternalLink size={12} /></a></div>
                <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "flex-end", gap: 7 }}><button className="secondary-button" disabled={busyTaskId === task.id} onClick={() => void updateTask(task.id, "dismissed")}>Dismiss</button><button className="primary-button" disabled={busyTaskId === task.id} onClick={() => void updateTask(task.id, "done")}><Check size={13} /> Done</button></div>
              </article>)}
            </div>}
          </section>
        </div>
      </main>

      {modalOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setModalOpen(false); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="import-title"><div className="modal-head"><div><h2 className="modal-title" id="import-title">Import an mbox archive</h2><p className="modal-caption">Messages are deduplicated by Message-ID.</p></div><button className="icon-button" aria-label="Close dialog" onClick={() => setModalOpen(false)}><X size={15} /></button></div><form className="modal-body" onSubmit={importMbox}><label className="form-field"><span className="form-label">Archive path in IMPORT_DIR</span><input className="form-input" name="path" placeholder="mailing-list.mbox" required /></label><div className="form-hint">Place the file in the server&apos;s configured import directory first. The API rejects paths outside that directory.</div><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setModalOpen(false)}>Cancel</button><button type="submit" className="primary-button"><FileUp size={14} /> Import archive</button></div></form></section></div>}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}