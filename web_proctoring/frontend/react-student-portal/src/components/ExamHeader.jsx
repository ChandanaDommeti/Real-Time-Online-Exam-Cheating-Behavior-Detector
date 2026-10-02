function formatTime(secondsLeft) {
  const mins = Math.floor(secondsLeft / 60)
    .toString()
    .padStart(2, "0");
  const secs = (secondsLeft % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
}

export default function ExamHeader({ secondsLeft, userName }) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex w-full max-w-[1400px] items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-100 text-brand-700 font-bold">
            PS
          </div>
          <div>
            <p className="m-0 text-lg font-extrabold tracking-tight text-slate-900">ProctorSuite</p>
            <p className="m-0 text-xs text-slate-500">Online Exam Portal</p>
          </div>
        </div>

        <div className="rounded-2xl border border-brand-100 bg-brand-50 px-6 py-2 text-center shadow-soft">
          <p className="m-0 text-xs font-semibold uppercase tracking-wide text-slate-500">Time Left</p>
          <p className="m-0 text-2xl font-extrabold text-brand-700">{formatTime(secondsLeft)}</p>
        </div>

        <div className="text-right">
          <p className="m-0 text-xs uppercase tracking-wide text-slate-400">Candidate</p>
          <p className="m-0 text-base font-semibold text-slate-800">{userName}</p>
        </div>
      </div>
    </header>
  );
}