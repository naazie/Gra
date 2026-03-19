/**
 * PrereqOnboarding.jsx
 *
 * Replaces the freeform back-and-forth prerequisite questions with a
 * structured, MCQ-style card flow rendered directly inside the chat.
 *
 * Flow
 * ----
 * 1.  Triggered when the AI detects an intent that needs context
 *     (e.g. "prepare for Google interview").
 * 2.  Shows ONE question at a time in a compact card so the user never
 *     feels overwhelmed.
 * 3.  On completion, serialises the answers into a single ingest payload
 *     and sends it to POST /memory/ingest, then calls onDone(summary).
 *
 * Props
 * -----
 *   username : string   — current user
 *   onDone   : fn(txt)  — called with a one-line summary to append to chat
 *   onSkip   : fn()     — called if user skips the whole flow
 */

import React, { useState } from "react";

const API = "http://localhost:8000";

/* ── Question bank ──────────────────────────────────────────────────────────
   Each question has:
     id        unique key
     q         question text shown to user
     multi     true = multi-select, false = single-select
     options   array of { value, label, emoji }
   ─────────────────────────────────────────────────────────────────────────*/
const QUESTIONS = [
  {
    id: "target_role",
    q: "What role are you preparing for?",
    multi: false,
    options: [
      { value: "swe_new_grad",  label: "SWE – New Grad",       emoji: "🎓" },
      { value: "swe_mid",       label: "SWE – Mid-level",      emoji: "💼" },
      { value: "swe_senior",    label: "SWE – Senior",         emoji: "🧠" },
      { value: "ml_engineer",   label: "ML / AI Engineer",     emoji: "🤖" },
    ],
  },
  {
    id: "target_company",
    q: "Which companies are you targeting?",
    multi: true,
    options: [
      { value: "google",    label: "Google",    emoji: "🔵" },
      { value: "meta",      label: "Meta",      emoji: "🟦" },
      { value: "amazon",    label: "Amazon",    emoji: "🟠" },
      { value: "microsoft", label: "Microsoft", emoji: "🪟" },
      { value: "startup",   label: "Startups",  emoji: "🚀" },
      { value: "other",     label: "Other",     emoji: "🏢" },
    ],
  },
  {
    id: "dsa_level",
    q: "How would you rate your DSA confidence?",
    multi: false,
    options: [
      { value: "beginner",     label: "Beginner – struggling with easy problems",  emoji: "🌱" },
      { value: "intermediate", label: "Comfortable with easy & medium",            emoji: "⚡" },
      { value: "advanced",     label: "Can solve most hard problems",              emoji: "🔥" },
      { value: "expert",       label: "Competitive programmer level",              emoji: "🏆" },
    ],
  },
  {
    id: "weak_areas",
    q: "Which topics feel weakest right now? (pick all that apply)",
    multi: true,
    options: [
      { value: "dp",            label: "Dynamic Programming",  emoji: "🧩" },
      { value: "graphs",        label: "Graphs / BFS / DFS",   emoji: "🕸️" },
      { value: "trees",         label: "Trees / BST / Heaps",  emoji: "🌳" },
      { value: "system_design", label: "System Design",        emoji: "🏗️" },
      { value: "backtracking",  label: "Backtracking",         emoji: "↩️" },
      { value: "bit_manip",     label: "Bit Manipulation",     emoji: "⚙️" },
    ],
  },
  {
    id: "timeline",
    q: "When is your interview?",
    multi: false,
    options: [
      { value: "1w",  label: "Within 1 week",  emoji: "🔴" },
      { value: "2w",  label: "1–2 weeks",      emoji: "🟠" },
      { value: "1m",  label: "This month",     emoji: "🟡" },
      { value: "3m+", label: "3+ months away", emoji: "🟢" },
    ],
  },
  {
    id: "practice_habit",
    q: "How consistent is your practice?",
    multi: false,
    options: [
      { value: "daily",    label: "Daily – I rarely miss a day",    emoji: "💪" },
      { value: "few_week", label: "A few times a week",             emoji: "📅" },
      { value: "binge",    label: "Binge then gaps",                emoji: "🎢" },
      { value: "restart",  label: "Just restarting after a break",  emoji: "🔄" },
    ],
  },
];

/* ── Helpers ────────────────────────────────────────────────────────────── */

function buildMemoryText(answers) {
  const lines = ["[Interview Prep Profile – auto-collected]"];
  QUESTIONS.forEach(({ id, q, options }) => {
    const val = answers[id];
    if (!val || (Array.isArray(val) && val.length === 0)) return;
    const vals  = Array.isArray(val) ? val : [val];
    const labels = vals.map(v => options.find(o => o.value === v)?.label ?? v);
    lines.push(`${q} → ${labels.join(", ")}`);
  });
  return lines.join("\n");
}

function buildSummary(answers) {
  const role     = answers.target_role   ? QUESTIONS[0].options.find(o => o.value === answers.target_role)?.label   : null;
  const timeline = answers.timeline      ? QUESTIONS[4].options.find(o => o.value === answers.timeline)?.label       : null;
  const weak     = (answers.weak_areas   || []).map(v => QUESTIONS[3].options.find(o => o.value === v)?.label).filter(Boolean);

  const parts = [];
  if (role)          parts.push(`targeting **${role}**`);
  if (timeline)      parts.push(`interview ${timeline.toLowerCase()}`);
  if (weak.length)   parts.push(`weak in: ${weak.slice(0, 3).join(", ")}`);

  return parts.length
    ? `✅ Profile saved — ${parts.join(" · ")}. I'll personalise your prep plan around this.`
    : "✅ Profile saved. I'll use this to guide your preparation.";
}

/* ── Sub-components ─────────────────────────────────────────────────────── */

function ProgressDots({ total, current }) {
  return (
    <div style={{ display: "flex", gap: 5, marginBottom: 14 }}>
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          style={{
            width: i === current ? 18 : 6,
            height: 6,
            borderRadius: 3,
            background: i < current
              ? "var(--teal)"
              : i === current
              ? "var(--blue)"
              : "var(--surface-4)",
            transition: "all 0.25s ease",
          }}
        />
      ))}
    </div>
  );
}

function OptionChip({ opt, selected, multi, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "9px 14px",
        borderRadius: "var(--r-md)",
        border: selected
          ? "1.5px solid var(--blue)"
          : "1px solid var(--border)",
        background: selected
          ? "rgba(79,142,247,0.12)"
          : "var(--surface-2)",
        color: selected ? "var(--text-primary)" : "var(--text-muted)",
        fontSize: 13,
        fontFamily: "var(--font)",
        cursor: "pointer",
        textAlign: "left",
        width: "100%",
        transition: "all 0.14s ease",
        boxShadow: selected ? "0 0 0 3px rgba(79,142,247,0.1)" : "none",
      }}
    >
      <span style={{ fontSize: 16, lineHeight: 1 }}>{opt.emoji}</span>
      <span style={{ flex: 1 }}>{opt.label}</span>
      {multi && (
        <span
          style={{
            width: 16,
            height: 16,
            borderRadius: 4,
            border: selected ? "1.5px solid var(--blue)" : "1px solid var(--border-hi)",
            background: selected ? "var(--blue)" : "transparent",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 10,
            color: "white",
            flexShrink: 0,
          }}
        >
          {selected ? "✓" : ""}
        </span>
      )}
      {!multi && (
        <span
          style={{
            width: 14,
            height: 14,
            borderRadius: "50%",
            border: selected ? "4px solid var(--blue)" : "1.5px solid var(--border-hi)",
            background: "transparent",
            flexShrink: 0,
          }}
        />
      )}
    </button>
  );
}

/* ── Main Component ─────────────────────────────────────────────────────── */

export default function PrereqOnboarding({ username, onDone, onSkip }) {
  const [step,      setStep]    = useState(0);
  const [answers,   setAnswers] = useState({});
  const [saving,    setSaving]  = useState(false);

  const q = QUESTIONS[step];
  const total = QUESTIONS.length;
  const current = answers[q.id];

  const hasAnswer = q.multi
    ? Array.isArray(current) && current.length > 0
    : Boolean(current);

  const toggle = (value) => {
    if (q.multi) {
      const prev = Array.isArray(answers[q.id]) ? answers[q.id] : [];
      const next = prev.includes(value)
        ? prev.filter(v => v !== value)
        : [...prev, value];
      setAnswers(a => ({ ...a, [q.id]: next }));
    } else {
      setAnswers(a => ({ ...a, [q.id]: value }));
    }
  };

  const isSelected = (value) => {
    const cur = answers[q.id];
    return q.multi
      ? Array.isArray(cur) && cur.includes(value)
      : cur === value;
  };

  const next = () => {
    if (step < total - 1) {
      setStep(s => s + 1);
    } else {
      finish();
    }
  };

  const back = () => { if (step > 0) setStep(s => s - 1); };

  const finish = async () => {
    setSaving(true);
    try {
      const memText = buildMemoryText(answers);
      await fetch(
        `${API}/memory/ingest?username=${encodeURIComponent(username)}&text=${encodeURIComponent(memText)}`,
        { method: "POST" }
      );
    } catch (_) {
      // Non-fatal — profile is best-effort
    } finally {
      setSaving(false);
      onDone(buildSummary(answers));
    }
  };

  const isLast = step === total - 1;

  return (
    <div
      style={{
        background: "var(--surface-1)",
        border: "1px solid var(--border-hi)",
        borderRadius: "var(--r-lg)",
        padding: "20px 22px",
        maxWidth: 480,
        width: "100%",
        boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
        animation: "slide-in 0.18s ease",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ fontSize: 15 }}>📋</span>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            Quick Profile · {step + 1} / {total}
          </span>
        </div>
        <button
          onClick={onSkip}
          style={{
            background: "none", border: "none", color: "var(--text-dim)",
            fontSize: 11, cursor: "pointer", fontFamily: "var(--font)", padding: "2px 6px",
            borderRadius: "var(--r-sm)",
          }}
        >
          Skip all ✕
        </button>
      </div>

      {/* Progress */}
      <ProgressDots total={total} current={step} />

      {/* Question */}
      <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 14, lineHeight: 1.45 }}>
        {q.q}
      </p>
      {q.multi && (
        <p style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 10, fontFamily: "var(--mono)" }}>
          Select all that apply
        </p>
      )}

      {/* Options */}
      <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 18 }}>
        {q.options.map(opt => (
          <OptionChip
            key={opt.value}
            opt={opt}
            multi={q.multi}
            selected={isSelected(opt.value)}
            onClick={() => toggle(opt.value)}
          />
        ))}
      </div>

      {/* Nav buttons */}
      <div style={{ display: "flex", gap: 8 }}>
        {step > 0 && (
          <button
            onClick={back}
            style={{
              padding: "9px 16px", background: "var(--surface-3)",
              border: "1px solid var(--border)", borderRadius: "var(--r-md)",
              color: "var(--text-muted)", fontSize: 13, cursor: "pointer",
              fontFamily: "var(--font)", transition: "all 0.14s",
            }}
          >
            ← Back
          </button>
        )}
        <button
          onClick={next}
          disabled={!hasAnswer || saving}
          style={{
            flex: 1, padding: "10px 20px",
            background: hasAnswer ? "var(--blue)" : "var(--surface-4)",
            border: "none", borderRadius: "var(--r-md)",
            color: hasAnswer ? "white" : "var(--text-dim)",
            fontSize: 13, fontWeight: 600, cursor: hasAnswer ? "pointer" : "not-allowed",
            fontFamily: "var(--font)", transition: "all 0.15s",
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? "Saving…" : isLast ? "Save Profile ✓" : "Next →"}
        </button>
      </div>
    </div>
  );
}