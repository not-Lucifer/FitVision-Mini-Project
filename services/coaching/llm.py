from services.config.workout_config import PROMPT


class LLMCoach:
    FALLBACK_MODELS = (
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b",
        "allam-2-7b",
    )

    def __init__(self, groq_client, preferred_model=None):
        self.client = groq_client
        self.history = []
        self.system_prompt = PROMPT
        self.preferred_model = preferred_model or self.FALLBACK_MODELS[0]

    def _fallback_text(self, event, issue):
        if issue:
            return (
                f"Good focus on the movement. {issue} "
                "Keep your form steady and complete the rep with control."
            )

        if event == "workout_started":
            return "Great start. Keep your movements controlled and stay consistent through the set."

        if event == "workout_completed":
            return "Excellent work. Keep your pace controlled and your form clean for the next set."

        return "Stay controlled and keep your form clean for a better workout."

    def give_feedback(self, event, issue):
        prompt = f"Event: {event}"

        if issue:
            prompt += f" Form Issue: {issue}"

        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.history[-10:],
            {"role": "user", "content": prompt}
        ]

        models_to_try = [self.preferred_model, *[m for m in self.FALLBACK_MODELS if m != self.preferred_model]]

        for model_name in models_to_try:
            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.4,
                )

                content = getattr(response.choices[0].message, "content", "") or ""
                text = str(content).strip()
                if text:
                    self.history.append({"role": "assistant", "content": text})
                    return text
            except Exception:  # pragma: no cover - defensive fallback for API/model issues
                continue

        text = self._fallback_text(event, issue)
        self.history.append({"role": "assistant", "content": text})
        return text
    