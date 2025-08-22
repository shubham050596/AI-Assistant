# gemini_question_generator.py

import google.generativeai as genai

# Configure with your actual Gemini API Key
genai.configure(api_key="AIzaSyBXKVhcNnKtotAh_hN6p1e0yfk61lqUDik")

model = genai.GenerativeModel("models/gemini-2.0-flash")


def generate_followup_question(answer: str) -> str:
    prompt = (
        "Given the following candidate's answer in an interview, suggest the next logical follow-up interview question. "
        "Be concise and job-relevant.\n\n"
        f"Answer: {answer}\n\n"
        "Follow-up Question:"
    )

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[Gemini Error] {e}")
        return ""
