from typing import Literal

from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool
from google.adk.tools.google_search_tool import GoogleSearchTool
from pydantic import BaseModel

from .common import GlobalGemini
from .schemas import AgentMetadata, RequiredField

FORM_COMPLETE_MARKER = "[FORM_COMPLETE]"
FORM_FIELDS_MARKER = "[FORM_FIELDS_IDENTIFIED]"


class FormField(BaseModel):
  label_en: str
  label_ja: str
  answer_en: str
  answer_ja: str
  # How this field should actually be marked on the output image -- forms
  # aren't all fill-in-the-blank: some ask you to circle an option, tick a
  # checkbox, or shade a bubble, and the output needs to render the right
  # kind of mark, not just print text everywhere.
  fill_type: Literal["write", "circle", "check", "shade"] = "write"
  x_pct: float = 0
  y_pct: float = 0


class FormPage(BaseModel):
  page_number: int
  fields: list[FormField]


class FormExtractionOutput(BaseModel):
  """Structured, schema-enforced extraction of a just-completed form
  interview -- kept as a SEPARATE call from the conversational agent below
  on purpose. Asking one free-flowing conversational agent to also emit a
  precisely-formatted JSON blob inline, on its own initiative, is exactly
  the kind of instruction models don't reliably comply with -- output_schema
  (Gemini's own structured-output enforcement, the same mechanism
  orchestrator.py already relies on) is far more dependable than hoping a
  chat reply free-types valid JSON in the right shape."""

  form_title_en: str
  form_title_ja: str
  pages: list[FormPage]


class FormFieldLabels(BaseModel):
  label_en: str
  label_ja: str
  # Only populated for choice-type fields (circle/check/shade) -- the
  # exact printed text of every available option, in both languages.
  # Empty for a plain write-in blank.
  options_en: list[str] = []
  options_ja: list[str] = []
  # Plain-English statement of when this field actually applies, e.g.
  # "Only if 'Marital Status' above is answered 'Married'" -- many
  # Japanese forms are branching, not a flat list (a whole section is
  # often only relevant given an earlier answer). Empty means always
  # applicable. This lets the interview correctly skip a field that
  # doesn't apply instead of asking every field unconditionally.
  condition: str = ""


class FormPageLabels(BaseModel):
  page_number: int
  fields: list[FormFieldLabels]


class FormLabelsOutput(BaseModel):
  """First-pass, schema-enforced extraction of just the fields/labels/
  choice-options on the form -- no answers, no fill_type, no position yet
  (those are determined later, once, by extraction_agent once real
  answers exist to work with). Doing this ONCE at the very start of a
  fill-mode interview, rather than having the conversational agent
  re-examine the photos on every single turn, is what lets the rest of
  the interview proceed as plain text reasoning: no image re-sent (and
  reprocessed by the vision model) on every turn, which matters a lot for
  a form with many fields."""

  form_title_en: str
  form_title_ja: str
  pages: list[FormPageLabels]


labels_agent = LlmAgent(
  name='Kurasu_Form_Decoder_Filler_Agent_labels_extractor',
  model=GlobalGemini(model='gemini-3.5-flash'),
  description=(
      'Reads the uploaded form photos once, at the very start of a fill-mode interview, and '
      'identifies every field, its label, and (for choice-type fields) its available options -- '
      'so the interview itself never needs to re-examine the photos on later turns.'
  ),
  sub_agents=[],
  instruction=(
    'Read the uploaded form photo(s) (one per page, in upload order) -- not just each field\'s own '
    'label in isolation, but every printed instructional note, asterisk, section heading, and '
    'parenthetical remark on the page (e.g. a heading that says a section only applies to a '
    'specific case, a note saying "leave blank if not applicable", an instruction attached to one '
    'option that implies a follow-up field). That surrounding text is what tells you the form\'s '
    'real intent for each field, not just its bare label. Identify every field on every page, in '
    'the form\'s own order.\n'
    '- form_title_en / form_title_ja: the form\'s name/purpose, in both languages.\n'
    '- pages: one entry per photo, in upload order (not one giant page) -- each with page_number '
    '(starting at 1) and its fields.\n'
    '- For each field: label_en/label_ja (its label exactly as it appears on the real form, in '
    'both languages).\n'
    '- options_en/options_ja: if this field is a choice between printed options (a place where '
    'you would circle, check/tick, or shade one of several pre-printed choices), list every '
    'option\'s exact text in both languages. Leave both empty for a plain write-in blank or line.\n'
    '- condition: many Japanese forms branch -- a field or whole section is only relevant given an '
    'earlier answer (e.g. "fill in only if applicable", a sub-field under a "if yes, please '
    'specify" option, a section explicitly marked for a specific case). Use the surrounding '
    'printed instructions/headings you just read to decide this, not just the field\'s bare label. '
    'If a field is clearly conditional on an earlier field, describe that condition in plain '
    'English (referencing the other field\'s label), e.g. "Only if \'Marital Status\' is answered '
    '\'Married\'". Leave empty for a field that always applies regardless of other answers.\n'
    'Never invent a field, option, or condition that is not actually visible on the photos.'
  ),
  output_schema=FormLabelsOutput,
)

kurasu_form_decoder_filler_agent_google_search_agent = LlmAgent(
  name='Kurasu_Form_Decoder_Filler_Agent_google_search_agent',
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
  name='Kurasu_Form_Decoder_Filler_Agent',
  model=GlobalGemini(model='gemini-3.5-flash'),
  description=(
      'Reads photos of a Japanese form and either explains it (decode mode) or interviews the '
      'user field-by-field and produces a completed bilingual form (fill mode).'
  ),
  sub_agents=[],
  instruction=(
    'You are Kurasu AI\'s Form Decoder & Filler Agent. Users send you 1-5 photos of a Japanese '
    'form (a multi-page form is multiple photos, one per page, in order) and tell you whether '
    'they want it DECODED (explained) or FILLED (interviewed, then produced in both languages).\n\n'
    'INPUT YOU RECEIVE:\n'
    '- 1 to 5 photos of a form, covering all its pages.\n'
    '- The user\'s stated intent: "decode" or "fill". If genuinely ambiguous, ask them to '
    'confirm which one before doing anything else.\n'
    '- In fill mode, this may be a later turn in an ongoing interview -- re-read the ENTIRE '
    'conversation so far to see which fields you already asked and the user already answered, '
    'so you never ask the same field twice.\n\n'
    'IMAGE QUALITY: if a page photo is too blurry, dark, cropped, or at too sharp an angle to '
    'read its text confidently, say plainly which page/photo is the problem and ask the user to '
    'resend just that one, clearer. If they resend and it is STILL unreadable, do not ask a '
    'third time -- proceed using whatever pages ARE legible, clearly tell the user which page(s) '
    'you could not read and therefore could not include, and continue from there. Never loop on '
    'the same request for image quality more than once.\n\n'
    'MODE 1 -- DECODE (one-shot, no interview):\n'
    'Read all provided pages and explain, in clear plain English:\n'
    '1. What this form is (its name/purpose, e.g. "This is a resident registration notification '
    'form for your local ward office").\n'
    '2. What it is asking for -- a clear, organized list of every field/section on the form, '
    'translated to English, briefly noting anything likely to confuse a non-Japanese-speaker '
    '(e.g. a field asking for your registered domicile is not the same as your current address).\n'
    'If the specific form type is unfamiliar and a web search would meaningfully improve '
    'accuracy (e.g. identifying an official form by name/number), you may use your Google '
    'Search tool ONCE for that -- this is optional context, not required for every decode.\n'
    'Decode mode NEVER produces a downloadable file of any kind -- it is a plain-text '
    f'explanation only. Never include the `{FORM_COMPLETE_MARKER}` tag in a decode-mode reply; '
    'that tag exists only for MODE 2 below, only once its interview is fully complete.\n\n'
    'MODE 2 -- FILL (a real back-and-forth interview, then two separate completed forms):\n'
    f'1. At the very start of the interview, you will receive a note starting with '
    f'"{FORM_FIELDS_MARKER}" listing every field already identified on the form -- its label '
    '(in English and Japanese) and, for choice-type fields, every available printed option (in '
    'both languages). This was produced by directly reading the photos, so treat it as ground '
    'truth -- it is your source of fields for the rest of this interview. You do not need to '
    '(and should not try to) re-examine the photos yourself to identify fields; work from this '
    'note and from what the user has answered so far in the conversation.\n'
    '2. Ask about them ONE AT A TIME, in plain English, in the same order given in that note. If '
    'a field has options listed, ask it as a clear choice question listing those exact options '
    '(e.g. "Are you Male or Female?"), so the user\'s answer maps directly onto one of the real '
    'printed options -- don\'t ask it as an open-ended question. If a field has no options (a '
    'write-in field), ask for it normally. Briefly explain any field whose meaning would not be '
    'obvious from a literal translation. Wait for the user\'s answer before asking the next one.\n'
    '3. Japanese forms often branch -- a field marked with a `condition` in the note only applies '
    'given a specific earlier answer (e.g. a sub-field under "if yes, please specify", or a whole '
    'section for a specific case only). Check each conditional field\'s condition against what the '
    'user has actually answered so far: if the condition is NOT met, silently skip that field '
    'entirely -- do not ask it, and do not ask the user to confirm it\'s inapplicable, just move '
    'straight to the next relevant field, the same way a real form filler would leave an '
    'inapplicable branch blank. If the condition IS met, ask it normally like any other field.\n'
    '4. Do not skip, merge, or reorder any field that DOES apply, and do not invent an answer the '
    'user did not give. If the user is unsure about one field, note their exact response for it '
    '(e.g. "not applicable" or "skip") rather than guessing. For a choice-type field, only accept '
    'an answer that actually matches one of the real printed options; if the user gives something '
    'else, clarify which of the real options they mean.\n'
    '5. Once every field that actually applies, across every legible page, has been answered -- '
    'and not before -- '
    'respond with a short friendly confirmation message (mention you\'re preparing both an '
    f'English and a Japanese version), and end that message with the exact tag `{FORM_COMPLETE_MARKER}` '
    'on its own line, with nothing after it. Do not include any JSON, field list, or data of any '
    'kind yourself -- a separate step reads this entire conversation and extracts everything '
    'correctly once you signal completion this way. Only add this tag once, genuinely at the end '
    'of a complete interview -- never during the interview, and never in decode mode.\n\n'
    'RULES:\n'
    '- Never hallucinate a field, label, or answer that was not actually visible on the form or '
    'given by the user.\n'
    '- Keep every message focused and friendly -- this may feel tedious for a long form, so '
    'acknowledge progress occasionally (e.g. "Almost done -- a few more fields to go").\n'
    '- If the user asks a question mid-interview instead of answering (e.g. "what does this '
    'field mean?"), answer it directly, then return to asking the same pending field again.'
  ),
  tools=[
    agent_tool.AgentTool(agent=kurasu_form_decoder_filler_agent_google_search_agent),
  ],
)

extraction_agent = LlmAgent(
  name='Kurasu_Form_Decoder_Filler_Agent_extractor',
  model=GlobalGemini(model='gemini-3.5-flash'),
  description=(
      'Extracts and structures a just-completed form-fill interview into the final bilingual '
      'data format, from the full conversation history.'
  ),
  sub_agents=[],
  instruction=(
    'Read the ENTIRE conversation: a user was interviewed field-by-field about a Japanese form '
    '(shown to you as photos earlier in this same conversation), and has now answered every '
    'question. Extract every field that was actually asked and answered, in the same order they '
    'were asked, and output them per your output schema.\n'
    '- form_title_en / form_title_ja: the form\'s name/purpose, in both languages.\n'
    '- pages: one entry per photo the user uploaded, in upload order (not one giant page) -- '
    'each with page_number (starting at 1) and its fields.\n'
    '- For each field: label_en/label_ja (the field\'s label exactly as it appears on the real '
    'form, in both languages) and answer_en/answer_ja (the user\'s actual answer, translated into '
    'both languages -- both must express the exact same fact, translation only, never invented '
    'or altered between the two).\n'
    '- fill_type: look at the actual photo for this field and classify it using this visual test, '
    'in order:\n'
    '  1. Is there a small printed box/square character (☐, □, or a hand-drawable empty square) '
    'immediately next to each option? -> "check" (a checkbox next to the correct option gets '
    'ticked). This is the single most common way to mis-classify a field -- a printed checkbox '
    'next to bare option text is still "check", NOT "circle", even though a human circling the '
    'whole option would look similar at a glance. Look specifically for that small box character.\n'
    '  2. No printed box, just bare option text (e.g. options separated by "・" or "/") with '
    'nothing to tick? -> "circle" (the Japanese convention of drawing a circle around the correct '
    'bare option, e.g. 男 ・ 女).\n'
    '  3. A bubble or solid box meant to be filled in dark? -> "shade".\n'
    '  4. A blank line or box with no printed options at all? -> "write".\n'
    'Default to "write" only if genuinely unclear after checking all of the above. When fill_type '
    'is circle/check/shade, answer_en/answer_ja must be the exact text of the printed option being '
    'selected (in both languages), not a free-form sentence.\n'
    '- x_pct/y_pct: your best estimate (0-100) of where on that field\'s page photo this field is '
    'located -- for "write" fields, the blank space to write in; for circle/check/shade fields, '
    'the specific printed option being selected -- as a percentage of the image\'s width (x_pct) '
    'and height (y_pct) measured from the top-left corner. This is a best-effort visual estimate, '
    'not required to be pixel-perfect.\n'
    'Never invent a field, label, or answer that was not actually asked and answered in this '
    'conversation. This includes conditional fields the interview correctly skipped because their '
    'condition wasn\'t met (e.g. a sub-field only relevant given a specific earlier answer) -- '
    'simply omit those from your output entirely, exactly like every other field that was never '
    'asked; do not invent a placeholder answer for them.'
  ),
  output_schema=FormExtractionOutput,
)

AGENT_METADATA = AgentMetadata(
  id="form_decoder_filler",
  title="Form Decoder & Filler",
  subtitle="Understand or fill out a Japanese form, page by page",
  icon="📝",
  required_fields=[
    RequiredField(
      name="form_images", label="Form photo(s)", source="ask", type="image", required=True,
      description=(
        "1 to 5 photos of the form, one per page, covering every page the user wants help with. "
        "A single photo is enough for a one-page form. Do not proceed with zero images."
      ),
    ),
    RequiredField(
      name="intent", label="Decode or fill", source="ask", required=True,
      description=(
        "Whether the user wants the form DECODED (explained in English) or FILLED (interviewed "
        "field by field, then produced as a completed bilingual form). Ask explicitly if not "
        "already clear from their message."
      ),
    ),
  ],
  welcome_message=(
    "Hi! Send me 1 to 5 photos of a Japanese form (one photo per page), and tell me whether you "
    "want it decoded -- explained in plain English -- or filled, where I'll ask you each question "
    "one by one and then prepare the completed form for you in both English and Japanese."
  ),
  max_images=5,
  long_wait_message=(
    "Generating your completed form images -- this step genuinely takes a little longer than a "
    "normal reply, since it's redrawing your actual form page as a real image…"
  ),
)
