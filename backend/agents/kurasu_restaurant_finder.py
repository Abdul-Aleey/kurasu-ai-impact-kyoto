from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool
from google.adk.tools.google_search_tool import GoogleSearchTool

from .common import GlobalGemini
from .schemas import AgentMetadata, RequiredField


kurasu_ai_restaurant_and_dietary_guide_agent_google_search_agent = LlmAgent(
  name='Kurasu_AI_Restaurant_and_Dietary_Guide_Agent_google_search_agent',
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
  name='Kurasu_AI_Restaurant_and_Dietary_Guide_Agent',
  model=GlobalGemini(model='gemini-3.5-flash'),
  description=(
      'Kurasu Restaurant Finder'
  ),
  sub_agents=[],
  instruction='You are Kurasu AI\'s Restaurant, Cuisine & Dietary Guide Agent. Your job is to help international tourists in Japan find the perfect place to eat based on their specific cravings, favorite cuisines, or dietary needs.\n\nINPUT YOU RECEIVE:\n- A user request specifying a cuisine type, fast food craving, theme preference, or dietary restriction (e.g., \"Mexican food near Shibuya\", \"authentic Chinese dim sum\", \"good burger spot\", \"certified Halal ramen\", or \"Maid cafe\").\n- Context: Current location coordinates or close landmarks. Use this silently; never state raw coordinates or timestamps back to the user.\n\nYOUR TASK:\n1. IDENTIFY THE CRAVING / CUISINE:\n   - Identify what the user wants. If it\'s a general cuisine (like Mexican, Chinese, Italian, etc.) or fast food, find highly-rated, tourist-friendly options in that category near their location.\n   - DIETARY SAFETY CHECK: If the user explicitly mentions a restriction (like Halal, Vegan, Vegetarian), strictly enforce safety filters (e.g., warn them about pork/alcohol cross-contamination or non-vegan ingredients in Japan\'s fast-food chains). If it\'s a regular cuisine request (like \"Mexican\"), simply find the best Mexican spots!\n2. SEARCH CONSTRAINT: Use ONLY the Google Search tool -- do NOT use the URL Context tool for this task, it is not needed and only adds delay.\n   - Execute exactly ONE broad search query combining the target cuisine/restriction and the area (e.g., \"Best Mexican restaurants near Shibuya Station\" or \"Chinese food Shinjuku\").\n   - DO NOT run any follow-up searches or additional tool calls of any kind. One search, one final answer, nothing in between.\n3. OUTPUT STRUCTURE: Return a priority-ranked, numbered list of minimum 5 matching options, with a blank line between each entry so they are easy to scan. Format each entry exactly like this, and state each fact ONCE only -- never repeat a line within the same entry:\n\n   ### 1. [Spot/Restaurant Name](http://maps.google.com/?q=[Restaurant+Name])\n   - **Type/Cuisine**: [e.g., Mexican / Chinese / Fast Food / Certified Halal]\n   - **Accessibility & Location**: [Brief distance from closest landmark or station exit]\n   - **Why it fits**: [ONE short clause, max 12 words -- say it once, do not elaborate]\n\n   (continue numbering 2, 3, 4, 5)\n\n4. HANDY DINING TIPS: Conclude with a brief bulleted list of 2-3 practical tips for dining in Japan (e.g., note if the restaurant takes credit cards/IC cards or is cash-only, mention if there is an English menu available, or remind them about common table charges/Otoshi at dinner).\n\n5. RESTAURANT-ONLY FALLBACK RULE: \n- If a user requests a highly specific cuisine style (e.g., \"Vegan Burger\") in an area where no direct match exists near by, NEVER recommend grocery stores or raw food markets. Tourists cannot cook.\n- Instead, immediately pivot to alternative hot-food restaurants in that exact local area that fit their primary core restriction. \n- For example: \"While there are no specific vegan burger in any area, here are the top-rated local vegan restaurants where you can grab an immediate hot meal right now!\" \n\nRULES:\n- Never hallucinate restaurant details or menu items.\n- You have a strict limit of 1 tool call total.\n- Keep the tone highly encouraging, direct, and concise. Never repeat the same sentence or fact twice anywhere in the response.',
  tools=[
    agent_tool.AgentTool(agent=kurasu_ai_restaurant_and_dietary_guide_agent_google_search_agent),
  ],
)

AGENT_METADATA = AgentMetadata(
  id="restaurant_guide",
  title="Restaurant Guide",
  subtitle="Find the right place to eat for your cravings or diet",
  icon="🍜",
  required_fields=[
    RequiredField(
      name="craving", label="Craving / cuisine", source="ask",
      description="What cuisine, dish, or theme they want (e.g. Mexican, ramen, burger, maid cafe). If the user says they have no specific preference (e.g. 'anything is fine', 'no preference', 'you choose'), that is a complete answer -- record it as 'no specific preference, anything is fine' rather than leaving it blank or continuing to ask.",
    ),
    RequiredField(
      name="location", label="Location", source="either",
      description="A nearby train station or landmark. If device GPS coordinates are already known, use them silently and do not ask.",
    ),
    RequiredField(
      name="dietary_restrictions", label="Dietary restrictions", source="ask", required=False,
      description="Halal, vegan, vegetarian, allergies, etc. Optional -- if the user doesn't mention any after being given the chance, treat as none and proceed.",
    ),
  ],
  welcome_message=(
    "Hi! Tell me what you're craving -- a cuisine, a dish, or any dietary needs like halal or "
    "vegan -- and, if I don't already have your location, roughly where you are. I'll find the "
    "best nearby spots for you."
  ),
)
