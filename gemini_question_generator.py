# gemini_question_generator.py
import os
import re  # <-- ADD THIS
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()




api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError("GOOGLE_API_KEY is not set")
genai.configure(api_key=api_key)

model = genai.GenerativeModel("models/gemini-2.0-flash")


def generate_followup_question(answer: str) -> str:
    prompt = (
        "Given the candidate's answer in an interview, suggest the next logical follow-up interview question. "
        "Be concise and job-relevant.\n\n"
        f"Answer: {answer}\n\n"
        "Follow-up Question:"
    )
    try:
        resp = model.generate_content(prompt)
        return (getattr(resp, "text", "") or "").strip()
    except Exception as e:
        print(f"[Gemini Error] {e}")
        return ""


def generate_seed_questions(resume_text: str, jd_text: str, n: int = 3) -> list[str]:
    prompt = (
        "You are an interviewer. Using the candidate resume and the job description, "
        "write concise, role-relevant interview questions. Avoid duplicates and keep them specific. "
        "Return one question per line with no numbering.\n\n"
        f"RESUME:\n{(resume_text or '')[:8000]}\n\n"
        f"JOB DESCRIPTION:\n{(jd_text or '')[:8000]}\n\n"
        f"Write {n} questions:"
    )
    try:
        resp = model.generate_content(prompt)
        text = (getattr(resp, "text", "") or "").strip()
        lines = [l.strip("-• \t") for l in text.splitlines() if l.strip()]
        out, seen = [], set()
        for l in lines:
            k = l.rstrip(" ?!.").lower()
            if k and k not in seen:
                out.append(l.rstrip())
                seen.add(k)
            if len(out) >= n:
                break
        return out
    except Exception as e:
        print(f"[Gemini Error] {e}")
        return []


def generate_score_and_feedback(
    resume_text: str,
    jd_text: str,
    transcript: list[tuple[str, str]],
    pass_threshold: int = 60,
) -> dict:
    """
    Returns:
      {
        "score": 0..100 (int),
        "verdict": "Pass"|"Reject",
        "reasons": [str, ...],
        "suggestions": [str, ...],
      }
    """
    # Build compact transcript
    qa = []
    for i, (q, a) in enumerate(transcript, 1):
        qa.append(f"Q{i}: {q}\nA{i}: {a}")
    transcript_text = "\n\n".join(qa)

    prompt = (
        "You are a technical interviewer scoring a candidate.\n"
        "Given the RESUME, JOB DESCRIPTION, and the Q/A TRANSCRIPT, produce:\n"
        "1) A single integer SCORE from 0 to 100 (no decimals).\n"
        "2) 3 concise REASONS supporting the score.\n"
        "3) 3 concise SUGGESTIONS for improvement.\n"
        "Be consistent, job-relevant, and conservative.\n"
        "Output strictly in this format:\n"
        "SCORE: <integer>\n"
        "REASONS:\n"
        "- <reason 1>\n"
        "- <reason 2>\n"
        "- <reason 3>\n"
        "SUGGESTIONS:\n"
        "- <tip 1>\n"
        "- <tip 2>\n"
        "- <tip 3>\n"
        f"\nRESUME:\n{(resume_text or '')[:8000]}"
        f"\n\nJOB DESCRIPTION:\n{(jd_text or '')[:8000]}"
        f"\n\nTRANSCRIPT:\n{transcript_text[:8000]}"
    )

    try:
        resp = model.generate_content(prompt)
        text = (getattr(resp, "text", "") or "").strip()
    except Exception as e:
        print(f"[Gemini Error] {e}")
        text = ""

    score = 0
    m = re.search(r"SCORE:\s*(\d+)", text, flags=re.I)
    if m:
        try:
            score = max(0, min(100, int(m.group(1))))
        except Exception:
            score = 0

    def bullets(section_name):
        pat = rf"{section_name}:\s*(?:\r?\n)+((?:-.*(?:\r?\n|$)){{1,10}})"
        m2 = re.search(pat, text, flags=re.I)
        if not m2:
            return []
        raw = m2.group(1).strip().splitlines()
        return [re.sub(r"^\s*-\s*", "", s).strip() for s in raw if s.strip()]

    reasons = bullets("REASONS")
    suggestions = bullets("SUGGESTIONS")

    verdict = "Pass" if score >= pass_threshold else "Reject"
    return {
        "score": score,
        "verdict": verdict,
        "reasons": reasons[:5],
        "suggestions": suggestions[:5],
    }




























