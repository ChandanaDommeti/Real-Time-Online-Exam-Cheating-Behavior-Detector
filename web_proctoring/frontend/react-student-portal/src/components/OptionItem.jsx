export default function OptionItem({ option, selected, onSelect }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        "group flex w-full items-center gap-4 rounded-2xl border p-4 text-left transition-all duration-200",
        selected
          ? "border-brand-500 bg-brand-50 shadow-soft"
          : "border-slate-200 bg-white hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-soft"
      ].join(" ")}
    >
      <span
        className={[
          "grid h-8 w-8 shrink-0 place-items-center rounded-lg border text-sm font-bold",
          selected
            ? "border-brand-600 bg-brand-600 text-white"
            : "border-slate-300 bg-slate-50 text-slate-700"
        ].join(" ")}
      >
        {option.key}
      </span>
      <span className="text-sm font-medium text-slate-800 sm:text-base">{option.value}</span>
    </button>
  );
}