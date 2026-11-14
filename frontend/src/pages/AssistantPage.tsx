import { Navigate } from "react-router-dom";
import { VoiceAssistant } from "../components/VoiceAssistant";
import { isSignedIn, useAuth } from "../hooks/useAuth";

const STUDENT_SUGGESTIONS = [
  "What's my attendance?",
  "What classes do I have tomorrow?",
  "Apply leave for next Monday",
  "Which placement drives can I register for?",
  "Explain normalisation from the DBMS notes",
];

const TEACHER_SUGGESTIONS = [
  "Show pending leave requests",
  "Which students are below 75% attendance?",
  "What classes am I advising today?",
];

export function AssistantPage() {
  const { me, loading } = useAuth();
  if (loading) return null;
  if (!isSignedIn(me) || !me) return <Navigate to="/login" replace />;

  const teacher = me.role === "teacher";
  const firstName = me.name?.split(" ")[0] ?? "there";
  const programme = { UG: "B.Tech", PG: "M.Tech" }[String(me.profile.programme)] ?? me.profile.programme;
  const details = [programme, me.profile.department, me.profile.class_code].filter(Boolean).join(", ");

  return (
    <div className="signed-in">
      <header className="page-head">
        <h1>Hello, {firstName}</h1>
        <p className="muted">{[teacher ? "Teacher" : "Student", details].filter(Boolean).join(", ")}</p>
      </header>
      <VoiceAssistant
        layout="wide"
        greeting={teacher ? "Hi! I can show your classes, attendance and pending requests." : "Hi! Ask about your attendance, timetable, rules, leave or placements."}
        suggestions={teacher ? TEACHER_SUGGESTIONS : STUDENT_SUGGESTIONS}
      />
    </div>
  );
}
