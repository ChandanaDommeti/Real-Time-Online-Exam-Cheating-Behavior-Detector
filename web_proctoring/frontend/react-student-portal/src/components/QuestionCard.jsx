import OptionItem from "./OptionItem";

export default function QuestionCard({
  question,
  questionIndex,
  selectedOption,
  onOptionSelect,
  onPrevious,
  onMarkReview,
  onClear,
  onSaveNext,
  onFinalSubmit,
  canPrevious
}) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft sm:p-6">
      <div className="mb-5 flex items-center justify-between gap-2">
        <p className="m-0 text-sm font-semibold uppercase tracking-wide text-brand-600">
          Question {questionIndex + 1}
        </p>
      </div>

      <h2 className="m-0 text-lg font-semibold leading-snug text-slate-900 sm:text-xl">{question.text}</h2>

      <div className="mt-5 space-y-3">
        {question.options.map((option) => (
          <OptionItem
            key={option.key}
            option={option}
            selected={selectedOption === option.key}
            onSelect={() => onOptionSelect(option.key)}
          />
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <button
          type="button"
          disabled={!canPrevious}
          onClick={onPrevious}
          className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={onMarkReview}
          className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-semibold text-amber-700 transition hover:bg-amber-100"
        >
          Mark for Review
        </button>
        <button
          type="button"
          onClick={onClear}
          className="rounded-xl border border-slate-300 bg-slate-50 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
        >
          Clear Response
        </button>
        <button
          type="button"
          onClick={onSaveNext}
          className="rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-brand-700"
        >
          Save & Next
        </button>
        <button
          type="button"
          onClick={onFinalSubmit}
          className="rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-slate-800"
        >
          Final Submit
        </button>
      </div>
    </section>
  );
}