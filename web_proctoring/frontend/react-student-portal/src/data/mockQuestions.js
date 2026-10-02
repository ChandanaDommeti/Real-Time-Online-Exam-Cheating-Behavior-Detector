const labels = ["A", "B", "C", "D"];

export const mockQuestions = Array.from({ length: 20 }, (_, idx) => ({
  id: idx + 1,
  text: `Question ${idx + 1}: Which option best answers this sample exam problem statement?`,
  options: labels.map((label) => ({
    key: label,
    value: `Option ${label} for question ${idx + 1}`
  }))
}));