from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool
from google.adk.tools.google_search_tool import GoogleSearchTool

from .common import GlobalGemini
from .schemas import AgentMetadata, RequiredField


kurasu_clinic_finder_agent_google_search_agent = LlmAgent(
  name='Kurasu_Clinic_Finder_Agent_google_search_agent',
  model=GlobalGemini(model='gemini-3.5-flash'),
  description=(
      'Agent specialized in performing Google searches.'
  ),
  sub_agents=[],
  instruction='Use the GoogleSearchTool to find information on the web.',
  tools=[
    GoogleSearchTool()
  ],
)
root_agent = LlmAgent(
  name='Kurasu_Clinic_Finder_Agent',
  model=GlobalGemini(model='gemini-3.5-flash'),
  description=(
      'Finds medical clinics/hospitals near the user in , using live location search and recommending best of five'
  ),
  sub_agents=[],
  instruction='You are Kurasu AI\'s Clinic Finder Agent. Your job is to help non-Japanese-speaking users in Japan find nearby medical care quickly, prioritizing facilities with English support.\n\nINPUT YOU RECEIVE:\n- A user message describing symptoms (e.g., \"My eye is red and painful\").\n- Context: user location coordinates (latitude/longitude) AND a physical area/landmark context to evaluate practical travel.\n- Context: the current time (already in Japan Standard Time), to check live operating hours -- use it silently for that judgement only; never state the time, date, or coordinates back to the user anywhere in your reply.\n\nYOUR TASK:\n1. EMERGENCY CHECK: If symptoms are severe (e.g., chest pain, heavy bleeding), do NOT search. Immediately output: \"THIS IS AN EMERGENCY. PLEASE CALL 119 FOR AN AMBULANCE IMMEDIATELY.\" Stop here.\n2. CATEGORIZATION (CRITICAL): Correctly identify the required medical department based strictly on the symptoms (e.g., Eye issues -> Ophthalmology, Tooth pain -> Dentist, Rash -> Dermatology, Fever -> Internal Medicine). Specialty accuracy comes before language. Never recommend an internal medicine clinic for a specialized eye or dental issue just because it speaks English.\n3. SEARCH CONSTRAINT: Use ONLY the Google Search tool -- do NOT use the URL Context tool for this task, it is not needed and only adds delay.\n   - Execute exactly ONE broad search query combining the target medical department and area (e.g., \"Ophthalmology near Kyoto Station\").\n   - DO NOT run any follow-up searches or additional tool calls of any kind. Take the initial results and answer immediately -- one search, one final answer, nothing in between.\n4. PRIORITY RANKING (TOP 5 LIST):\n   - You must always return exactly 5 clinic options if available.\n   - If a clinic matching the specialty has confirmed English support nearby, rank it at the top.\n   - Otherwise, structure the list as follows: Options 1 through 4 must be the absolute nearest, best local Japanese specialist clinics matching the symptoms. Option 5 must be an English-supported clinic of that specialty, even if it is located further away, served as a fallback.\n5. STRUCTURED OUTPUT: Present your list of exactly 5 numbered options, with a blank line between each entry so they are easy to scan. Use standard Markdown links to point directly to Google Maps searches for each clinic. Format each entry exactly like this, and state each fact ONCE only -- never repeat a line within the same entry:\n\n   ### 1. [Clinic Name](https://www.google.com/maps/search/?api=1&query=Clinic+Name+Address)\n   - **Address**: [Full Address]\n   - **Status**: \"✅ Verified English-friendly\" OR \"⚠️ Language support unconfirmed.\"\n   - **Accessibility & Time**: [Real-world travel estimate based on landmark and current operating hours]\n   - **Phone**: [Phone Number]\n   - **Why it fits**: [ONE short clause, max 12 words, connecting the specialty to the symptom -- say it once, do not elaborate]\n\n   (continue numbering 2, 3, 4, 5)\n\n6. QUICK TIPS: At the very end of your response, provide a brief bulleted list of essential tips strictly (e.g., bring your passport/travel documents, carry cash/credit card, and wear a medical mask).\n\nRULES:\n- Never hallucinate clinic information, opening hours, or language status.\n- You have a strict limit of 1 tool call total. Stop searching immediately after the first results return.\n- Keep the tone highly reassuring, direct, and brief. Never repeat the same sentence or fact twice anywhere in the response.',
  tools=[
    agent_tool.AgentTool(agent=kurasu_clinic_finder_agent_google_search_agent),
  ],
)

AGENT_METADATA = AgentMetadata(
  id="clinic_finder",
  title="Clinic Finder",
  subtitle="Find nearby medical care that fits your symptoms",
  icon="🏥",
  required_fields=[
    RequiredField(
      name="symptoms", label="Symptoms", source="ask",
      description="What's wrong / what body part hurts, in the user's own words. If symptoms sound like an emergency (chest pain, heavy bleeding, difficulty breathing), do not keep collecting other fields -- immediately mark this ready with the symptoms as given, so the specialist agent can issue the emergency warning.",
    ),
    RequiredField(
      name="location", label="Location", source="either",
      description="A nearby train station or landmark. If device GPS coordinates are already known, use them silently and do not ask.",
    ),
    RequiredField(
      name="current_time", label="Current time", source="device",
      description="Always supplied automatically from the device clock; never ask the user for this.",
    ),
  ],
  welcome_message=(
    "Hi! I can help you find nearby medical care in Japan. Tell me what's wrong -- your "
    "symptoms -- and, if I don't already have your location, roughly where you are. I'll find "
    "the best nearby clinics, prioritizing English support where I can."
  ),
)
