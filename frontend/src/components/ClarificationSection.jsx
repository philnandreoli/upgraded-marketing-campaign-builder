import { useState } from "react";
import { submitClarification } from "../api";

export default function ClarificationSection({
  questions,
  savedAnswers,
  campaignId,
  status,
  onSubmitted,
  readOnly = false,
}) {
  const [answers, setAnswers] = useState({});

  // Merge local draft answers with persisted answers from the backend
  const resolvedAnswer = (id) =>
    (answers[id] || "").trim() || (savedAnswers && savedAnswers[id]) || "";
  const [submitting, setSubmitting] = useState(false);

  const isWaiting = status === "clarification" && !readOnly;

  const setAnswer = (id) => (e) =>
    setAnswers((prev) => ({ ...prev, [id]: e.target.value }));

  const allAnswered =
    questions?.length > 0 &&
    questions.every((q) => resolvedAnswer(q.id).length > 0);

  const answeredCount = questions
    ? questions.filter((q) => resolvedAnswer(q.id).length > 0).length
    : 0;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await submitClarification(campaignId, answers);
      onSubmitted?.();
    } catch (err) {
      alert("Failed to submit answers: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (!questions || questions.length === 0) {
    if (status === "clarification") {
      return (
        <div className="card">
          <h2>💬 Strategy Clarification</h2>
          <div className="loading">
            <span className="spinner" /> Analysing brief…
          </div>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="card clarify-card">
      {/* Header */}
      <div className="clarify-header">
        <div className="clarify-header-text">
          <h2>💬 Strategy Clarification</h2>
          <p className="clarify-subtitle">
            The Strategy Agent has a few questions before building your campaign
            strategy. Your answers will help produce a more targeted plan.
          </p>
        </div>
        {isWaiting && (
          <div className="clarify-progress">
            <span className="clarify-progress-label">
              {answeredCount}/{questions.length} answered
            </span>
            <div className="clarify-progress-track">
              <div
                className="clarify-progress-fill"
                style={{
                  width: `${(answeredCount / questions.length) * 100}%`,
                }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Questions */}
      <form onSubmit={handleSubmit} className="clarify-form">
        {questions.map((q, i) => {
          const isAnswered = resolvedAnswer(q.id).length > 0;
          return (
            <div
              key={q.id}
              className={`clarify-question${isWaiting ? " editable" : ""}${isAnswered ? " answered" : ""}`}
            >
              <div className="clarify-question-number">{i + 1}</div>
              <div className="clarify-question-body">
                <p className="clarify-question-text">{q.question}</p>
                {q.why && (
                  <p className="clarify-question-why">
                    <span className="clarify-why-label">Why:</span> {q.why}
                  </p>
                )}
                {isWaiting ? (
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <textarea
                      className="clarify-textarea"
                      placeholder="Your answer…"
                      value={answers[q.id] || ""}
                      onChange={setAnswer(q.id)}
                      rows={3}
                    />
                  </div>
                ) : (
                  <div className="clarify-answer-display">
                    {resolvedAnswer(q.id) || <em className="clarify-no-answer">(no answer recorded)</em>}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {isWaiting && (
          <div className="clarify-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!allAnswered || submitting}
            >
              {submitting ? (
                <>
                  <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                  Submitting…
                </>
              ) : (
                "Submit Answers & Continue →"
              )}
            </button>
            {!allAnswered && (
              <span className="clarify-hint">
                Please answer all questions to continue
              </span>
            )}
          </div>
        )}
      </form>
    </div>
  );
}
