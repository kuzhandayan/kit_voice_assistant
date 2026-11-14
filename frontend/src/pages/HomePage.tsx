import { useEffect, useState } from "react";
import { api, type College, type Course } from "../api/client";
import { VoiceAssistant } from "../components/VoiceAssistant";
import { rupees } from "../lib/format";

const SUGGESTIONS = [
  "What courses do you offer?",
  "What marks do I need for CSE?",
  "What documents do I need for admission?",
  "I want to apply for admission",
];

export function HomePage() {
  const [data, setData] = useState<{ college: College; courses: Course[] } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.home().then(setData).catch(() => setFailed(true));
  }, []);

  return (
    <div className="home">
      <section className="hero">
        <div className="hero__text">
          <h1>{data?.college.name ?? "Knotopian Institute of Technology"}</h1>
          <p className="hero__tagline">{data?.college.tagline ?? "Excellence in Engineering and Applied Technology"}</p>
          <p className="hero__intro">
            {data?.college.description ??
              "An autonomous engineering institution in Coimbatore, Tamil Nadu."}
          </p>
          <p className="hero__hint">
            Thinking of joining? Ask about courses, fees, eligibility and dates, or apply, just by talking.
          </p>
        </div>
        <div className="hero__assistant">
          <h2 className="panel-title">Talk to us</h2>
          <VoiceAssistant greeting="Hi! Ask me anything about admissions at KIT." suggestions={SUGGESTIONS} />
        </div>
      </section>

      <section className="courses" aria-labelledby="courses-title">
        <h2 id="courses-title">Courses for 2027–28</h2>
        {failed && <p className="notice">Course details couldn't load. The assistant can still answer your questions.</p>}
        {data && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Programme</th>
                  <th scope="col" className="num">Minimum 12th marks</th>
                  <th scope="col" className="num">Annual fee</th>
                  <th scope="col" className="num">Hostel fee</th>
                  <th scope="col" className="num">Seats</th>
                </tr>
              </thead>
              <tbody>
                {data.courses.map((c) => (
                  <tr key={c.code}>
                    <th scope="row">
                      {c.name}
                      <span className="code">{c.code}</span>
                    </th>
                    <td className="num">{c.min_12th_percent}%</td>
                    <td className="num">{rupees(c.annual_fee)}</td>
                    <td className="num">{rupees(c.hostel_fee)}</td>
                    <td className="num">{c.seats}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && (
          <p className="contact">
            Admissions office: <a href={`tel:${data.college.contact.phone.replace(/\s/g, "")}`}>{data.college.contact.phone}</a>,{" "}
            <a href={`mailto:${data.college.contact.email}`}>{data.college.contact.email}</a>. {data.college.contact.address}
          </p>
        )}
      </section>
    </div>
  );
}
