"use client";

import { useCallback, useRef, useState } from "react";
import ScreeningCard, { ScreenResult } from "./ScreeningCard";
import { STRINGS, Lang } from "@/lib/i18n";

export default function Explorer({ lang }: { lang: Lang }) {
  const t = STRINGS[lang];
  const s = t.screen;
  const [q, setQ] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [sugOpen, setSugOpen] = useState(false);
  const [sugActive, setSugActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScreenResult | null>(null);
  const debounceRef = useRef<number | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);

  // Debounced address typeahead against /api/suggest (city address points).
  const fetchSuggestions = useCallback(async (query: string) => {
    const qq = query.trim();
    if (qq.length < 3) {
      setSuggestions([]);
      setSugOpen(false);
      return;
    }
    try {
      const res = await fetch(`/api/suggest?q=${encodeURIComponent(qq)}`);
      const json = (await res.json()) as { suggestions?: string[] };
      const list = json.suggestions ?? [];
      setSuggestions(list);
      setSugOpen(list.length > 0);
      setSugActive(-1);
    } catch {
      setSuggestions([]);
      setSugOpen(false);
    }
  }, []);

  function onChange(v: string) {
    setQ(v);
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => fetchSuggestions(v), 350);
  }

  async function runScreen(address: string) {
    const a = address.trim();
    if (!a || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setSugOpen(false);
    try {
      const res = await fetch(`/api/v1/screen?address=${encodeURIComponent(a)}&lang=${lang}`);
      const json = await res.json();
      if (!res.ok) {
        setError(typeof json.error === "string" ? json.error : s.lookupError);
        return;
      }
      setResult(json as ScreenResult);
      window.setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 60);
    } catch {
      setError(s.lookupError);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    runScreen(sugActive >= 0 && suggestions[sugActive] ? suggestions[sugActive] : q);
  }

  function pickSuggestion(addr: string) {
    setQ(addr);
    setSugOpen(false);
    runScreen(addr);
  }

  return (
    <div>
      <form className="addrform" onSubmit={onSubmit}>
        <div className="addrwrap">
          <input
            value={q}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => { if (suggestions.length > 0) setSugOpen(true); }}
            onBlur={() => window.setTimeout(() => setSugOpen(false), 120)}
            onKeyDown={(e) => {
              if (!sugOpen || suggestions.length === 0) return;
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSugActive((a) => (a + 1) % suggestions.length);
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setSugActive((a) => (a - 1 + suggestions.length) % suggestions.length);
              } else if (e.key === "Enter" && sugActive >= 0) {
                e.preventDefault();
                pickSuggestion(suggestions[sugActive]);
              } else if (e.key === "Escape") {
                setSugOpen(false);
              }
            }}
            placeholder={t.addressPlaceholder}
            aria-label={t.addressPlaceholder}
            autoComplete="off"
          />
          {sugOpen && suggestions.length > 0 && (
            <ul className="sugbox" role="listbox" aria-label={t.suggestLabel}>
              {suggestions.map((addr, i) => (
                <li
                  key={addr}
                  role="option"
                  aria-selected={i === sugActive}
                  className={`sugitem${i === sugActive ? " active" : ""}`}
                  onMouseDown={(e) => { e.preventDefault(); pickSuggestion(addr); }}
                  onMouseEnter={() => setSugActive(i)}
                >
                  {addr}
                </li>
              ))}
            </ul>
          )}
        </div>
        <button type="submit" disabled={loading}>
          {loading ? t.searching : t.searchButton}
        </button>
      </form>
      <p className="examples">
        {t.exampleAddresses}{" "}
        {["407 Arlington Ave", "401 Arlington Ave", "409 Arlington Ave"].map((a, i) => (
          <span key={a}>
            {i > 0 && " · "}
            <button className="linklike" type="button" onClick={() => { setQ(a); runScreen(a); }}>
              {a}
            </button>
          </span>
        ))}
      </p>
      <p className="herostats">{t.heroStats}</p>

      {error && <div className="error" role="alert">{error}</div>}

      <div ref={resultRef}>
        {result ? (
          <ScreeningCard result={result} t={t} />
        ) : (
          !error && <p className="examples" style={{ marginTop: 24 }}>{s.noScreenYet}</p>
        )}
      </div>
    </div>
  );
}
