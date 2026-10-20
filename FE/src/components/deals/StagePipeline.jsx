import { Check } from "lucide-react";
import { STAGES } from "../../lib/constants";
import { classNames } from "../../lib/format";

const FLOW = STAGES.filter((s) => s.key !== "terminated");

export default function StagePipeline({ stage, onChange, disabled }) {
  const current = FLOW.findIndex((s) => s.key === stage);
  const terminated = stage === "terminated";
  return (
    <ol className={classNames("pipeline", terminated && "terminated")}>
      {FLOW.map((step, index) => {
        const state = terminated ? "" : index < current ? "done" : index === current ? "current" : "";
        return (
          <li key={step.key} className={state}>
            <button type="button" disabled={disabled || !onChange} onClick={() => onChange?.(step.key)} title={`Move to ${step.label}`}>
              <span className="pipeline-dot">{state === "done" ? <Check size={11} /> : index + 1}</span>
              <span className="pipeline-label">{step.label}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
