# Dynamic question-paper extraction

The exporter now uses flexible question records rather than a fixed MCQ/short/long
template. Existing GPU OCR and Word rendering are unchanged.

## Default: rules, no additional model required

The detector reads the question span for option evidence rather than assuming
options occur within a fixed number of OCR blocks. Numbered matching, true/false,
and fill-blank tasks own their subparts; their type does not become a heading for
later questions. Descriptive subparts remain in the question text. Repeated
question numbers after OR/अथवा remain in the same question. These are structural
rules, not subject-specific or question-number-specific templates. The default
is still heuristic, not an enabled language model or a guarantee for unseen papers.

Restart the application with the usual local or Wi-Fi launcher. Upload a PDF and
download Excel. The default does not send document text to a remote AI service.

- Recognizes additional headings, Q-prefixed numbers, numeric/subquestion/roman
  numbers, parenthesized and dotted letter options, and numeric options in MCQs.
- Groups the same question type into one sheet. Numbered fill-blank tasks retain their subparts in one row; OR/अथवा alternatives stay with their parent question.
- Creates columns for the actual option labels, not a fixed A–D set.
- Extracts explicitly stated `3 marks` / `3 अंक` values. When the paper explicitly identifies margin numbers as marks, isolated or punctuation-delimited trailing marks are supported. Other bare numbers or ambiguous
  section-wide marking schemes remain blank rather than receiving default 2/5 marks.
- Embedded Latin symbols stay with the dominant language of the sentence. No Original question/option columns are exported. Script detection is not translation.
- Exports the cover and question sheets only: no review/source tabs, source comments or frozen panes. Instructions are excluded from the cover and question tables.
- Saves an `_analysis.json` file beside Word/Excel, with source block references.

Rules remain heuristics. Numbered instructions can become unknown question
candidates; repeated numbers are retained and flagged instead of silently merged.
Matching lists, case studies, and unrecognized subquestion layouts retain source
text but are not guaranteed to become fully structured specialized tables.
Always review unfamiliar papers against the original PDF. OCR omissions cannot be
recovered from text alone. The analysis JSON preserves recognized text, not original images.

## Optional AI: two stages using one configured model

`paper_analyzer.py` first requests a provisional section plan, then extracts
question records from bounded groups of OCR blocks with boundary context.
`model_client.py` calls an OpenAI-compatible chat-completions endpoint supporting
JSON-schema response format. This is a protocol choice, not a selected provider.
No model has been installed or selected as part of this change.

Example PowerShell configuration for an already-running local model server:

```powershell
$env:PAPER_ANALYSIS_MODE = "ai"
$env:PAPER_AI_URL = "http://127.0.0.1:11434/v1/chat/completions"
$env:PAPER_AI_MODEL = "YOUR_INSTALLED_MODEL_NAME"
.\start_surya_local.cmd
```

For a deliberately selected cloud service, set its HTTPS chat-completions URL,
model name, `PAPER_AI_API_KEY`, and `PAPER_AI_ALLOW_REMOTE=1`. This sends recognized
document text to that endpoint. Do not commit API keys. Remote mode is disabled
unless explicitly enabled. The chosen model/provider's license and data terms
require separate review.

AI failures, invalid schemas, oversized input blocks, or missing configuration
fall back to rules with an explicit review note. Long questions exceeding boundary
context may require review. Valid JSON does not establish factual correctness:
text evidence, marks evidence, references, and duplicates are checked separately.

To return to the default:

```powershell
$env:PAPER_ANALYSIS_MODE = "rules"
```

## Regenerate without rerunning OCR

```powershell
.\.venv\Scripts\python.exe code\export_documents.py "output\surya\YOUR_FILE_surya.json" --destination "output\reviewed"
```

Reuse a saved or manually reviewed analysis:

```powershell
.\.venv\Scripts\python.exe code\export_documents.py "output\surya\YOUR_FILE_surya.json" --structured-input "output\reviewed\YOUR_FILE_analysis.json" --destination "output\reviewed"
```

The saved source blocks must match the supplied OCR input. Review flags are
retained. AI-mode validation is not a guarantee of content completeness.

## Code map

- `question_schema.py`: Pydantic records, options, source references, language text.
- `paper_analyzer.py`: flexible rules, section planning, chunked optional AI extraction.
- `model_client.py`: configured endpoint, request limits, remote-use opt-in.
- `question_validation.py`: evidence checks and review coverage.
- `dynamic_excel.py`: record-driven sheets and source/review exports.
- `document_parser.py`: flexible public entry point; legacy parser remains available.
- `export_documents.py`: analyze, validate, save records, export documents.
- `surya_lan_server.py`: pipeline progress and downloadable analysis JSON.

Tests cover schema/AI failures using controlled responses. Live AI accuracy and
speed must be benchmarked after selecting a model. Existing OCR model licensing
conditions still apply; this change does not alter them.
