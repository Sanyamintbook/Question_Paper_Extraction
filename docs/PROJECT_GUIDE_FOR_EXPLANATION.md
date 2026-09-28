# Mintbook OCR: Project Guide

This guide explains the current project in simple language. Use it to understand the system, demonstrate it, and answer technical questions.

## 1. What the project does

Mintbook OCR converts scanned question-paper PDFs into editable Word and Excel files.

The application performs five main stages:

1. A user uploads a PDF through the local web page.
2. Surya OCR reads every page and returns text, layout blocks, reading order, and coordinates.
3. The question analyzer identifies questions, languages, options, marks, question types, sections, and OR/अथवा alternatives.
4. Validation checks that extracted records are supported by the original OCR text.
5. Exporters create an editable Word document and a dynamically structured Excel workbook.

The source PDF is never edited. The raw OCR JSON remains the source of truth.

The interface supports either one PDF or a folder of PDFs. Folder mode creates a browser-side batch and sends each PDF through the same tested single-document pipeline. Generated files are written into a user-approved output folder.

## 2. The complete data flow

```text
PDF upload
   ↓
Mintbook web server
   ↓
Surya OCR page recognition
   ↓
Raw page JSON + page cache
   ↓
Question-level rule analysis
   ↓
Pydantic records and validation
   ↓
Word output + dynamic Excel output + validation JSON
```

The browser does not perform OCR itself. It starts Python processes and displays their progress.

## 3. Main approach and why it was used

### Local OCR

Surya OCR runs locally. This supports scanned PDFs and Indian languages while keeping question papers on the computer. It also avoids depending on a paid cloud OCR API for the normal workflow.

### Page-by-page processing and caching

Each recognized page is saved separately before the final document is assembled. This was chosen because large PDFs take time. If processing stops, completed pages can be reused instead of starting again.

### Full-page recognition with adaptive recovery

The normal path recognizes the complete page so layout and reading order are preserved. If a page fails, stalls, or produces an incomplete result, the recovery path divides it into overlapping regions. Only a failed region is divided again. Overlap results are de-duplicated before saving.

This approach protects normal pages from unnecessary splitting while allowing difficult dense pages to finish.

### Question-level dynamic classification

The system classifies each question from its own wording and structure. A section heading is only supporting context.

Examples:

- options such as A, B, C and D indicate an MCQ;
- “fill in the blanks” or “रिक्त स्थान” indicates fill-in-the-blank;
- “true or false” or “सत्य/असत्य” indicates true/false;
- “match the following” or “मिलान” indicates matching;
- “explain”, “describe”, “write”, and similar words indicate a descriptive question.

This was selected because exam papers do not follow one fixed template. Question type may change inside the same section.

### Evidence-first extraction

Every structured question stores references to the OCR blocks from which it came. Validation checks extracted text, marks, option labels, and question numbers against those blocks. The code does not invent missing text, translate content, or guess unsupported marks.

### Optional AI analysis

An optional schema-constrained model client exists, but it is not enabled by default. The normal path is rule-based. If AI mode fails or returns invalid information, the system falls back to the rule analyzer.

This makes the default workflow local, testable, and reproducible while keeping an extension point for future model-assisted analysis.

## 4. Important files

### Application entry points

| File | Responsibility | Why it exists |
|---|---|---|
| `start_surya_local.cmd` | Starts Mintbook OCR on this computer at port 8502 without a URL token. | Gives a simple double-click/local command. |
| `start_surya_wifi.cmd` | Starts the same-Wi-Fi version. | Allows approved users on the local network to access the application. |
| `start_surya_lan_ui.ps1` | PowerShell launcher for the LAN server. | Keeps Windows startup configuration outside Python. |
| `run_surya.py` | Compatibility launcher that runs `code/run_surya.py`. | Existing commands continue working after code was organized. |
| `export_documents.py` | Compatibility launcher that runs `code/export_documents.py`. | Preserves the original export command. |

### User interface and job management

#### `code/surya_lan_server.py`

This is the Mintbook OCR web application.

It contains:

- the HTML and CSS interface;
- PDF upload validation;
- local or same-Wi-Fi HTTP handling;
- the processing queue;
- progress parsing;
- calls to the OCR and export programs;
- secure download handling;
- optional access-token checking.

It also owns the browser-side batch workflow:

- switch between **One PDF** and **PDF folder**;
- collect PDFs from a selected folder;
- ignore non-PDF files;
- request write permission for an output folder;
- upload and monitor one PDF at a time;
- save Word, Excel and analysis JSON files into the selected folder.

Only one worker consumes the queue, so multiple people may submit files without starting several heavy OCR processes simultaneously. Their jobs wait and run one by one.

### Batch folder processing

Folder input uses the browser’s `webkitdirectory` and `multiple` attributes. The browser returns the files inside the chosen folder, including files in nested folders. JavaScript filters that list to `.pdf` files and sorts it before processing.

The output location uses the File System Access API:

```javascript
window.showDirectoryPicker({mode: "readwrite"})
```

The browser returns a directory handle after the user grants permission. The application never receives unrestricted permission to the computer and does not rely on a typed Windows path.

The batch loop performs this sequence for every PDF:

```text
Upload one PDF
→ receive job ID
→ poll until completed
→ download each generated output
→ write it through the approved directory handle
→ continue with the next PDF
```

Sequential processing was selected because OCR can consume substantial CPU, GPU and memory. Reusing the existing single-PDF endpoint also avoids maintaining two different OCR pipelines.

Folder saving requires a current Chromium browser such as Microsoft Edge or Google Chrome and a secure browser context: `localhost` during local use or HTTPS in deployment.

### OCR engine and reliability

#### `code/run_surya.py`

This is the main OCR pipeline.

Important responsibilities:

- loads PDF pages;
- initializes the Surya recognition model;
- configures the local inference backend;
- calculates a PDF fingerprint;
- creates a page cache;
- recognizes normal pages;
- detects blank or incomplete results;
- applies timeouts and watchdogs;
- performs adaptive split recovery;
- merges and de-duplicates overlapping blocks;
- writes final JSON and plain text safely.

The file uses atomic writes: data is first written safely and then moved into place. This prevents an interrupted run from leaving a partially written cache file that looks complete.

### OCR text normalization

#### `code/structured_output.py`

Converts Surya HTML blocks into logical lines. It keeps math markers, separates combined options, and preserves reading order. This is the bridge between OCR layout output and clean Word/question parsing.

#### `code/document_parser.py`

Contains shared text helpers and the previous/compatibility question parser. Current `parse_questions()` delegates to the new dynamic analyzer, so older callers still work.

### Dynamic question analysis

#### `code/question_schema.py`

Defines the structured data model using Pydantic:

- `SourceBlock`: original OCR evidence;
- `Option`: one option label and multilingual text;
- `QuestionRecord`: question number, type, text, options, marks, source references, and review notes;
- `Analysis`: all questions, sources, method, notes, and optional plan.

Pydantic rejects unexpected or invalid fields. This prevents loosely shaped data from silently entering the exporters.

#### `code/question_structure.py`

Contains reusable structural rules. It determines when explicit question wording should override a section hint, recognizes subparts, retains composite questions, and looks ahead for real choice evidence.

#### `code/paper_analyzer.py`

This is the core question parser.

It:

- converts OCR blocks into source records;
- finds question numbers;
- separates MCQ options;
- detects question type per question;
- joins bilingual versions;
- keeps subquestions with their parent;
- keeps OR/अथवा inside the same question;
- extracts marks only when supported by visible evidence;
- preserves unclassified text in the source records;
- optionally calls the AI client and falls back to rules if needed.

OCR sometimes places many short- or long-answer questions inside one multiline `ListGroup`. The analyzer checks the first logical line to recognize that such a block starts with a numbered question, then splits every numbered question inside it. A numbered question on the same page also ends instruction-skipping mode when a short- or long-answer section is already known. Verbs such as “explain” and “define” preserve that known short/long category instead of reducing it to generic descriptive.

#### `code/question_validation.py`

Checks the structured analysis against source OCR. It flags missing source links, empty text, incomplete MCQs, duplicate labels, repeated question numbers, and unsupported marks. It also creates the machine-readable validation report.

#### `code/model_client.py`

Optional client for a local or explicitly allowed remote OpenAI-compatible endpoint. It requires a Pydantic JSON schema, disables random temperature, limits response size, and blocks accidental remote document transfer unless it is explicitly enabled.

### Document export

#### `code/export_documents.py`

Coordinates Word and Excel export.

For Word, it:

- recreates the readable page order;
- adds headings and indentation;
- converts supported equations into editable Word equations;
- removes duplicated blocks;
- removes standalone margin marks such as repeated `1` values when the paper declares marks in the margin;
- retains original text if equation conversion fails.

For Excel, it passes validated analysis to the dynamic workbook generator.

#### `code/dynamic_excel.py`

Creates Excel sheets from detected question types.

It:

- groups questions by their own detected type;
- creates only the option columns that exist;
- creates separate sheets for MCQ, fill blanks, true/false, matching, and descriptive questions;
- keeps OR/अथवा with its parent question;
- gives matching questions separate Column A and Column B fields;
- preserves multilingual columns;
- applies the established blue theme and readable sizing;
- prevents OCR text beginning with `=` from becoming an Excel formula.

#### `code/word_math.py`

Converts LaTeX recognized by OCR into MathML and then into Word OMML equations. If conversion fails, it inserts readable text instead of dropping the equation.

#### `code/excel_math.py`

Converts common LaTeX expressions into readable Unicode for Excel and Word fallbacks, such as fractions, powers, subscripts, degree symbols, and Greek letters.

### Testing and evaluation

| Location | Purpose |
|---|---|
| `tests/test_dynamic_extraction.py` | Tests dynamic question types, bilingual content, OR/अथवा, matching columns, validation, and Excel export. |
| `tests/test_improvements.py` | Tests OCR recovery, option splitting, math conversion, Word output, and Windows backend handling. |
| `tests/test_lan_server.py` | Tests upload names, progress parsing, processing stages, and Mintbook UI labels. |
| `code/evaluate_output.py` | Performs simple output-count/text checks on saved OCR results. |
| `reports/` | Contains corpus audits and saved-OCR validation results. |

The current automated suite contains **50 passing tests** across question analysis, Word/Excel export, OCR recovery, Windows process handling, the Mintbook interface and folder-based batch processing.

The corpus audit covers **762 PDF files and 13,873 pages**, including **642 unique PDFs** and **120 exact duplicate files**. It also identified sparse/image-heavy and damaged files that require separate review; an audit count is not a claim that every page was manually verified.

## 5. Main libraries

| Library | Use in this project | Reason for selection |
|---|---|---|
| `surya-ocr` | OCR, layout recognition, reading order, multilingual text. | Designed for document OCR and broad language coverage. |
| `pypdfium2` | Opens and renders PDF pages. | Efficient local PDF rendering used by the OCR pipeline. |
| `BeautifulSoup4` | Reads and normalizes HTML returned in OCR blocks. | Safely extracts structured text and lists from OCR HTML. |
| `Pydantic` | Validates question and analysis records. | Provides strict schemas and clear validation. |
| `python-docx` | Creates editable Word files. | Supports paragraphs, formatting, and Word XML integration. |
| `openpyxl` | Creates styled Excel workbooks. | Supports dynamic sheets, cell styles, sizing, and safe `.xlsx` output. |
| `latex2mathml` | Converts LaTeX math to MathML. | First stage of editable Word equation conversion. |
| `mathml2omml` | Converts MathML to Word equation XML. | Produces native editable equations in Word. |
| `lxml` | Manipulates equation XML. | Required to insert OMML safely into Word documents. |
| Python standard `http.server` | Serves the Mintbook web page and API. | Keeps the local UI lightweight without adding a web framework. |
| Python `threading` and `queue` | Runs jobs and reports progress. | Separates browser requests from long OCR processing and limits heavy concurrent work. |

## 6. CPU and GPU use

The project can use both CPU and GPU depending on the installed backend and configuration.

- PDF reading, file handling, parsing, validation, Word generation, and Excel generation mainly use the CPU.
- OCR model inference uses the configured local inference backend.
- `code/run_surya.py` checks backend availability and configures GPU layers when supported.
- If GPU acceleration is unavailable, inference can fall back to CPU.

Using both does not mean every operation runs on both devices at the same time. Each stage uses the suitable resource.

## 7. Output folders

| Folder | Contents |
|---|---|
| `input/` | PDFs supplied to command-line runs. |
| `output/surya_pages/` | Resumable per-page OCR cache. |
| `output/surya/` | Consolidated raw OCR JSON and text. |
| `output/documents/` | Command-line Word and Excel exports. |
| `runtime/lan_jobs/` | Isolated input and output files for web-interface jobs. |
| `reports/` | Audit and validation reports. |

Internal folders still use historical `surya` names. The customer-facing product name is Mintbook OCR. Renaming internal paths would require a migration so existing caches and commands are not broken.

## 8. What “dynamic” means here

Dynamic means the output is not tied to one hard-coded paper template.

The parser uses evidence from each question. The Excel workbook then builds sheets and columns from the detected records. This supports changing question order, question numbering, languages, option counts, and mixed question types.

Dynamic does not mean perfect interpretation of every possible damaged scan. OCR quality and ambiguous paper layout can still affect results. The system preserves source evidence and review notes instead of silently inventing an answer.

## 9. Common questions and suggested answers

### What problem does this solve?

“It converts scanned multilingual question papers into editable Word and structured Excel files. The main challenge is recognizing both the text and the question structure across papers with different layouts.”

### Is this only Surya OCR?

“Surya is the OCR engine. Our application adds resumable processing, failure recovery, question-level classification, source validation, Word and dynamic Excel generation, and the Mintbook web interface.”

### Why did you use rules instead of relying entirely on AI?

“The rule path is local, repeatable, easy to test, and does not invent text. It uses explicit evidence such as question numbers, option labels, task wording, and language scripts. An optional schema-constrained AI path exists for future use, with rule fallback.”

### How are different paper patterns handled?

“The parser detects each question independently. It does not assume that every question in a section has the same type. Section headings provide context, but explicit question wording and structure take priority.”

### How is OR/अथवा handled?

“It is appended to the current parent question. It does not create a new sheet or an unrelated question.”

### How are matching questions exported?

“They get a separate Matching sheet. Explicit Column A and Column B headings or visible paired separators are used to divide the content. If the OCR evidence is unclear, the original text is retained rather than guessed.”

### How do you prevent data loss?

“Raw OCR JSON is preserved. Each question links back to source block IDs. Page results are cached with atomic writes, and unclear data is retained with review information.”

### What happens when one page fails?

“The pipeline can retry it, restart a stalled local backend, and switch to adaptive region recovery. Completed pages remain cached, and later pages can continue.”

### Why does processing take time?

“OCR inference is computationally expensive, especially on dense scanned pages. The application also validates pages, may recover failed regions, analyzes every question, and creates Word and Excel outputs.”

### Can several people use it?

“Several people can open the same-Wi-Fi interface and submit jobs. Jobs are queued and processed one at a time to prevent multiple OCR models from exhausting the machine’s memory.”

### How does folder processing work?

“The browser collects PDF files from the chosen input folder and processes them sequentially. Each PDF uses the normal server job API. When a job finishes, the browser writes its Word, Excel and analysis files into the output folder for which the user granted permission.”

### Why can the user not type an output path?

“A website is not permitted to write freely to an arbitrary path on the user’s computer. The browser’s folder picker gives the application a controlled directory handle only after explicit user approval.”

### Is the optional AI sending files online?

“Not in the default rules mode. Remote AI transfer is blocked unless an HTTPS endpoint and an explicit allow setting are configured.”

### What are the current limitations?

“Very poor scans, unusual numbering, missing OCR layout, or visually ambiguous matching columns may need review. The project is designed to retain uncertain text rather than hide it.”

### Is the current application ready for public internet deployment?

“The present `http.server` application is appropriate for local and controlled pilot use. A public customer service still needs production authentication, a persistent database and queue, private object storage, HTTPS infrastructure, rate limits, monitoring, retention controls and isolated OCR workers.”

## 10. A short explanation for a meeting

“Mintbook OCR is a local Python application for scanned multilingual question papers. Surya OCR extracts page text and layout. Our page-level pipeline adds caching, timeouts, and adaptive split recovery. After OCR, our analyzer classifies every question independently using wording, option structure, numbering, and language evidence. Pydantic models hold the structured records, and validation links them back to the raw OCR source. The exporters then create editable Word files and dynamic Excel sheets for MCQ, fill blanks, true/false, matching, and descriptive questions. The default workflow is rule-based and local, while an optional schema-constrained AI client is available for future use.”

## 11. Recommended learning order

Read and explain the project in this order:

1. `code/surya_lan_server.py` — how the user starts a job.
2. `code/run_surya.py` — how OCR and recovery work.
3. `code/question_schema.py` — what one structured question contains.
4. `code/question_structure.py` — shared classification rules.
5. `code/paper_analyzer.py` — how OCR becomes questions.
6. `code/question_validation.py` — how results are checked.
7. `code/export_documents.py` — how output generation is coordinated.
8. `code/dynamic_excel.py` and `code/word_math.py` — how final files are built.
9. `tests/` — examples that prove the behavior.

Do not try to memorize every line first. Learn the data flow, the responsibility of each file, and the reason behind each design choice. Then study one file at a time.
