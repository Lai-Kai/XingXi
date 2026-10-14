import { useState } from "react";
import { hydrateRoot } from "react-dom/client";

import { ManualEvaluations } from "@/components/workspace/manual-evaluations";

function Preview() {
  const [cases, setCases] = useState(window.demoSnapshot.cases);
  const [runs, setRuns] = useState(window.demoSnapshot.runs);
  const [observations, setObservations] = useState({});
  return <ManualEvaluations
    cases={cases} runs={runs} observations={observations} saving={false}
    onObservation={(value) => setObservations((current) => ({ ...current, [value.case_id]: value }))}
    onCreateCase={async (input) => setCases((current) => [{ ...input, id: crypto.randomUUID(), active: true, created_by: "offline-preview", created_at: new Date().toISOString() }, ...current])}
    onRun={async () => {
      const results = cases.filter((item) => item.active).map((item) => {
        const value = observations[item.id];
        const failure_reasons = [];
        if (!value?.answer?.trim()) failure_reasons.push("empty answer");
        if (value.actual_status !== item.expected_status) failure_reasons.push(`expected status ${item.expected_status}, got ${value.actual_status}`);
        if (value.citation_count < item.min_citations) failure_reasons.push(`expected at least ${item.min_citations} citations`);
        const missing = item.required_terms.filter((term) => !value.answer.includes(term));
        if (missing.length) failure_reasons.push(`missing required terms: ${missing.join(", ")}`);
        return { ...value, passed: failure_reasons.length === 0, failure_reasons };
      });
      const passed = results.filter((item) => item.passed).length;
      setRuns((current) => [{ id: crypto.randomUUID(), status: "completed", created_by: "offline-preview", created_at: new Date().toISOString(), release_id: null, total: results.length, passed, pass_rate: passed / results.length, results }, ...current]);
    }}
  />;
}

hydrateRoot(document.getElementById("demo"), <Preview />);
