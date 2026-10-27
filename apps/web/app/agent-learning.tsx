"use client";
import { useEffect, useRef, useState } from "react";
import { api, display } from "./workspace-schema";

type Lesson = {
  id: string;
  title: string;
  reference_title: string;
  paragraphs: string[];
  questions: { id: string; prompt: string; options: string[] }[];
};
type Result = {
  correct_count: number;
  question_count: number;
  feedback: { question_id: string; correct: boolean; explanation: string }[];
};
function LessonCard({ lesson, version }: { lesson: Lesson; version: string }) {
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);
  useEffect(
    () => () => {
      request.current++;
    },
    [],
  );
  return (
    <details className="card">
      <summary>{lesson.title}</summary>
      {lesson.paragraphs.map((text, index) => (
        <p key={index}>{text}</p>
      ))}
      <p className="muted">مرجع محصول: {lesson.reference_title}</p>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          const sequence = ++request.current;
          setBusy(true);
          setError("");
          setResult(null);
          try {
            const value = await api(
              `agent-workbench/lessons/${lesson.id}/check`,
              "POST",
              { version, answers },
            );
            if (request.current === sequence) setResult(value);
          } catch (failure) {
            if (request.current === sequence) setError(String(failure));
          } finally {
            if (request.current === sequence) setBusy(false);
          }
        }}
      >
        {lesson.questions.map((question) => (
          <fieldset key={question.id} disabled={busy}>
            <legend>{question.prompt}</legend>
            {question.options.map((option, index) => (
              <label key={index}>
                <input
                  type="radio"
                  name={`${lesson.id}-${question.id}`}
                  value={index}
                  required
                  checked={answers[question.id] === index}
                  onChange={() => {
                    setAnswers({ ...answers, [question.id]: index });
                    setResult(null);
                  }}
                />
                {option}
              </label>
            ))}
          </fieldset>
        ))}
        <button disabled={busy}>
          {busy ? "در حال بررسی…" : "بررسی پاسخ‌ها"}
        </button>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {result && (
        <div role="status">
          <p>
            پاسخ درست: {display(result.correct_count)} از{" "}
            {display(result.question_count)}
          </p>
          {result.feedback.map((feedback) => (
            <p key={feedback.question_id}>
              {feedback.correct ? "درست: " : "نیازمند اصلاح: "}
              {feedback.explanation}
            </p>
          ))}
        </div>
      )}
    </details>
  );
}
export function AgentLearning() {
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [version, setVersion] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    api("agent-workbench/lessons")
      .then((value) => {
        if (current) {
          setLessons(value.lessons);
          setVersion(value.version);
        }
      })
      .catch((failure) => {
        if (current) setError(String(failure));
      });
    return () => {
      current = false;
    };
  }, []);
  return (
    <section className="card" aria-label="آموزش پایهٔ سیستم">
      <h2>آموزش پایهٔ سیستم</h2>
      <p>
        درس‌های مستند محصول و خودارزیابی قطعی؛ بدون تولید متن با مدل یا نیاز به
        حسابداری.
      </p>
      <p className="muted">
        این تمرین گواهی یا تأیید مالی نیست. پاسخ‌ها و پیشرفت ذخیره نمی‌شوند.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!lessons.length && !error && <p role="status">در حال دریافت درس‌ها…</p>}
      {lessons.map((lesson) => (
        <LessonCard key={lesson.id} lesson={lesson} version={version} />
      ))}
    </section>
  );
}
