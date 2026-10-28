import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "";

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
}

function App() {
  const [flags, setFlags] = useState([]);
  const [stats, setStats] = useState({ hourly: [], reviews: [] });
  const [error, setError] = useState("");
  const [loadingDemo, setLoadingDemo] = useState(false);

  async function refresh() {
    try {
      setError("");
      const [nextFlags, nextStats] = await Promise.all([
        request("/flags?reviewed=false"),
        request("/stats"),
      ]);
      setFlags(nextFlags);
      setStats(nextStats);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function review(id, decision) {
    await request(`/flags/${id}/review`, {
      method: "POST", body: JSON.stringify({ decision }),
    });
    await refresh();
  }

  async function summarize(id) {
    const result = await request(`/flags/${id}/summary`, { method: "POST" });
    setFlags((items) => items.map((item) => item.id === id ? { ...item, summary: result.summary } : item));
  }

  async function loadDemo() {
    try {
      setLoadingDemo(true);
      setError("");
      await request("/demo/seed", { method: "POST" });
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingDemo(false);
    }
  }

  return (
    <main className="content">
      {error && <div className="error">{error}</div>}
      <section className="welcome">
        <p className="eyebrow">FRAUD REVIEW</p>
        <h1>Good evening, Analyst</h1>
        <p className="intro">Review model-flagged transactions and make the final call.</p>
        <button className="demo-button" onClick={loadDemo} disabled={loadingDemo}>
          {loadingDemo ? "Loading demo..." : "Load demo transactions"}
        </button>
      </section>

      <section className="metrics">
        <div className="metric-card"><span>Open flags</span><strong>{flags.length}</strong></div>
        <div className="metric-card"><span>Reviewed cases</span><strong>{stats.reviews.reduce((sum, row) => sum + row.n, 0)}</strong></div>
        <div className="metric-card"><span>Highest score</span><strong>{flags.length ? flags[0].score.toFixed(4) : "—"}</strong></div>
      </section>

      <section className="section-heading">
        <div><p className="eyebrow">RECENT FLAGS</p><h2>Review queue</h2></div>
        <span className="soft-count">{flags.length} open</span>
      </section>

      <section className="queue">
        {flags.length === 0 ? <div className="empty"><h3>Your queue is quiet</h3><p>Load demo transactions to see how Sentinel explains suspicious activity.</p></div> : flags.map((flag) => (
          <article className="flag" key={flag.id}>
            <div className="flag-top">
              <div><span className="pill">{flag.source === "model" ? "MODEL FLAG" : "FALLBACK RULE"}</span><h3>Transaction #{flag.id}</h3></div>
              <div className="score-wrap"><span>Risk score</span><strong className="score">{flag.score.toFixed(4)}</strong></div>
            </div>
            <p className="muted">Amount <b>${flag.amount.toFixed(2)}</b> · Hour {flag.hour_of_day} · Top signals: <b>{flag.explanation?.map((e) => e.feature).join(", ") || "No explanation"}</b></p>
            {flag.summary && <p className="summary">{flag.summary}</p>}
            <div className="actions">
              <button onClick={() => summarize(flag.id)}>Generate summary</button>
              <button className="danger" onClick={() => review(flag.id, "confirm_fraud")}>Confirm fraud</button>
              <button className="secondary" onClick={() => review(flag.id, "dismiss")}>Dismiss</button>
            </div>
          </article>
        ))}
      </section>

      <section className="panel chart-panel">
        <div className="panel-heading"><p className="eyebrow">PATTERN</p><h2>Transactions by hour</h2></div>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={stats.hourly}>
            <CartesianGrid strokeDasharray="3 3" stroke="#dedbd1" />
            <XAxis dataKey="hour_of_day" stroke="#817d73" />
            <YAxis stroke="#817d73" />
            <Tooltip />
            <Bar dataKey="flagged_n" fill="#bd5c3b" name="Flagged" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
