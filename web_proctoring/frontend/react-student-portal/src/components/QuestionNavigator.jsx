const statusStyles = {
  not_answered: "bg-slate-100 text-slate-600 border-slate-200",
  answered: "bg-emerald-100 text-emerald-700 border-emerald-200",
  review: "bg-amber-100 text-amber-700 border-amber-200",
  not_answered_review: "bg-violet-100 text-violet-700 border-violet-200"
};

const legendItems = [
  { key: "not_answered", label: "Not Answered" },
  { key: "answered", label: "Answered" },
  { key: "review", label: "Answered + Marked for Review" },
  { key: "not_answered_review", label: "Not Answered + Marked for Review" }
];

export default function QuestionNavigator({ statuses, currentIndex, onQuestionSelect }) {
  return (
    <aside className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft sm:p-6">
      <h3 className="m-0 text-base font-bold uppercase tracking-wide text-slate-700">Questions</h3>

      <div className="mt-4 max-h-[460px] overflow-y-auto pr-1">
        <div className="grid grid-cols-5 gap-2">
          {statuses.map((status, idx) => {
            const isCurrent = idx === currentIndex;
            return (
              <button
                key={idx + 1}
                type="button"
                onClick={() => onQuestionSelect(idx)}
                className={[
                  "rounded-xl border px-2 py-2 text-xs font-bold transition-all duration-200",
                  statusStyles[status],
                  isCurrent ? "ring-2 ring-brand-500 ring-offset-1" : "hover:-translate-y-0.5"
                ].join(" ")}
                aria-label={`Question ${idx + 1}`}
              >
                Q{idx + 1}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-3">
        <p className="m-0 mb-3 text-sm font-semibold text-slate-700">Legend</p>
        <div className="space-y-2">
          {legendItems.map((item) => (
            <div key={item.key} className="flex items-center gap-2 text-sm text-slate-700">
              <span className={["h-3.5 w-3.5 rounded-sm border", statusStyles[item.key]].join(" ")} />
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}