import { useEffect, useMemo, useState } from "react";
import ExamHeader from "./components/ExamHeader";
import QuestionCard from "./components/QuestionCard";
import QuestionNavigator from "./components/QuestionNavigator";
import { mockQuestions } from "./data/mockQuestions";

const EXAM_DURATION_SECONDS = 25 * 60;

function getQuestionStatus(answer, markedForReview) {
  if (markedForReview && answer) return "review";
  if (markedForReview && !answer) return "not_answered_review";
  if (answer) return "answered";
  return "not_answered";
}

export default function App() {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [secondsLeft, setSecondsLeft] = useState(EXAM_DURATION_SECONDS);
  const [answers, setAnswers] = useState({});
  const [reviewFlags, setReviewFlags] = useState({});

  const question = mockQuestions[currentIndex];

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSecondsLeft((prev) => (prev <= 1 ? 0 : prev - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const statuses = useMemo(
    () =>
      mockQuestions.map((q) =>
        getQuestionStatus(Boolean(answers[q.id]), Boolean(reviewFlags[q.id]))
      ),
    [answers, reviewFlags]
  );

  const handleOptionSelect = (optionKey) => {
    setAnswers((prev) => ({ ...prev, [question.id]: optionKey }));
  };

  const handlePrevious = () => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const handleMarkReview = () => {
    setReviewFlags((prev) => ({ ...prev, [question.id]: !prev[question.id] }));
  };

  const handleClearResponse = () => {
    setAnswers((prev) => {
      const next = { ...prev };
      delete next[question.id];
      return next;
    });
  };

  const handleSaveNext = () => {
    setCurrentIndex((prev) => Math.min(mockQuestions.length - 1, prev + 1));
  };

  const handleFinalSubmit = () => {
    const answeredCount = Object.keys(answers).length;
    window.alert(`Exam submitted. Attempted: ${answeredCount}/${mockQuestions.length}`);
  };

  return (
    <div className="min-h-screen bg-slate-100">
      <ExamHeader secondsLeft={secondsLeft} userName="Chandana" />

      <main className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <QuestionCard
            question={question}
            questionIndex={currentIndex}
            selectedOption={answers[question.id] || ""}
            onOptionSelect={handleOptionSelect}
            onPrevious={handlePrevious}
            onMarkReview={handleMarkReview}
            onClear={handleClearResponse}
            onSaveNext={handleSaveNext}
            onFinalSubmit={handleFinalSubmit}
            canPrevious={currentIndex > 0}
          />

          <QuestionNavigator
            statuses={statuses}
            currentIndex={currentIndex}
            onQuestionSelect={setCurrentIndex}
          />
        </div>
      </main>
    </div>
  );
}