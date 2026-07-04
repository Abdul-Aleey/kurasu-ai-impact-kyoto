// Mirrors FORM_FIELDS_MARKER in backend/agents/kurasu_form_decoder_filler.py.
// The backend deterministically appends this marker + a JSON field list to
// a mid-interview reply so it persists into the next turn's replayed
// history (letting the form-filler interview skip re-sending the photo on
// every turn) -- it's bookkeeping, never meant for the user to see.
const FORM_FIELDS_MARKER = "[FORM_FIELDS_IDENTIFIED]";

export function stripFormFieldsNote(text: string): string {
  const index = text.indexOf(FORM_FIELDS_MARKER);
  return index === -1 ? text : text.slice(0, index).trim();
}
