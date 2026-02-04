"""
Chat service for Gemini-powered employee consultation.
"""
import google.generativeai as genai
from ..config import Config


class ChatService:
    """Handles AI-powered chat for employee consultation."""

    SYSTEM_PROMPT = """You are a helpful HR/staffing consultant assistant for a company. Your role is to help users find the best employees for projects based on their skills, scores, and availability.

Guidelines:
- Be concise and direct in your responses
- Lower capacity % means more available; higher utilization % means more actively engaged
- Scores are out of 10 - consider 7+ as strong, 5-7 as moderate, below 5 as developing
- Current Engagements shows the projects/clients an employee is currently working on
- If asked about skills or data not available, say so clearly

IMPORTANT OUTPUT FORMAT - Follow this exactly:
When listing employees, use this format for each person:

**EmployeeName**
- Skill Name: score/10 (rating)
- Capacity: X% (availability level)

Example:
**John**
- Generative AI: 7.2/10 (Strong)
- Capacity: 25% (Highly Available)

**Sarah**
- Generative AI: 6.8/10 (Moderate)
- Capacity: 40% (Available)

End with a brief summary paragraph explaining why these employees are recommended.

NEVER use markdown tables, colons before names, or numbered lists for employees.

Available employee data is provided below. Only use this data to answer questions."""

    def __init__(self, data_service):
        self.data_service = data_service
        self.model = None
        self._initialize_model()

    def _initialize_model(self):
        """Initialize the Gemini model if API key is available."""
        api_key = Config.get_gemini_api_key()
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(
                Config.GEMINI_MODEL,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                )
            )

    def is_available(self) -> bool:
        """Check if chat service is available."""
        return self.model is not None

    def chat(self, question: str, chat_history: list = None) -> dict:
        """
        Process a chat message and return a response.

        Args:
            question: The user's question
            chat_history: List of previous messages [{"role": "user/assistant", "content": "..."}]

        Returns:
            dict with 'answer' or 'error'
        """
        if not self.is_available():
            return {"error": "Chat service is not configured. Please set GEMINI_API_KEY."}

        if not question or not question.strip():
            return {"error": "Please enter a question."}

        try:
            # Build the context with employee data
            employee_context = self.data_service.build_context_for_chat()

            # Build conversation history for context
            messages = []

            # Add system context as first message
            context_message = f"{self.SYSTEM_PROMPT}\n\n--- EMPLOYEE DATA ---\n{employee_context}\n--- END DATA ---"
            messages.append({"role": "user", "parts": [context_message]})
            messages.append({"role": "model", "parts": ["I understand. I have access to the employee data and I'm ready to help you find the best employees for your projects. How can I assist you?"]})

            # Add chat history
            if chat_history:
                for msg in chat_history[-5:]:  # Keep last 5 messages for context
                    role = "user" if msg["role"] == "user" else "model"
                    messages.append({"role": role, "parts": [msg["content"]]})

            # Add current question
            messages.append({"role": "user", "parts": [question]})

            # Generate response
            response = self.model.generate_content(messages)

            return {"answer": response.text}

        except Exception as e:
            print(f"Chat error: {e}")
            return {"error": f"Failed to generate response: {str(e)}"}

    def get_quick_suggestions(self) -> list:
        """Get quick suggestion prompts for the user."""
        return [
            "Who are the top performers overall?",
            "Find employees for a GenAI project",
            "Who has the most availability?",
            "Compare skills across the team",
        ]
