"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { splitSkillInput, type TalentSearchState } from "@/lib/marketplace/search";

export function TalentSearchForm({ initial }: { initial: TalentSearchState }) {
  const router = useRouter();
  const [query, setQuery] = useState(initial.query);
  const [skills, setSkills] = useState(initial.skills.join(", "));
  const [available, setAvailable] = useState(
    initial.available === null ? "any" : initial.available ? "true" : "false",
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    for (const skill of splitSkillInput(skills)) params.append("skill", skill);
    if (available !== "any") params.set("available", available);
    router.push(`/talent${params.size ? `?${params.toString()}` : ""}`);
  }

  function reset() {
    setQuery("");
    setSkills("");
    setAvailable("any");
    router.push("/talent");
  }

  return (
    <form className="talent-search-form" onSubmit={submit}>
      <label className="talent-search-main">
        <span>Search expertise</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Product designer, Python engineer, motion…"
          maxLength={160}
          autoComplete="off"
        />
      </label>
      <label>
        <span>Skills</span>
        <input
          value={skills}
          onChange={(event) => setSkills(event.target.value)}
          placeholder="Python, React"
          autoComplete="off"
        />
      </label>
      <label>
        <span>Availability</span>
        <select value={available} onChange={(event) => setAvailable(event.target.value)}>
          <option value="any">Any status</option>
          <option value="true">Accepting work</option>
          <option value="false">Unavailable</option>
        </select>
      </label>
      <button className="talent-search-submit" type="submit">Search talent</button>
      <button className="talent-search-reset" type="button" onClick={reset}>Reset</button>
    </form>
  );
}
