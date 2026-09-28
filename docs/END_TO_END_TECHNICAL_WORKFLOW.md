# Mintbook OCR: End-to-End Technical Workflow

This document follows one PDF through the complete application. It starts with the high-level business flow and then drills down to files, functions, folders, processes, data structures, conditions, and failure handling.

## 1. Workflow at the highest level

```text
User selects a PDF
        ↓
Web application validates and stores the upload
        ↓
Job enters a queue
        ↓
OCR reads each PDF page
        ↓
OCR pages are validated and saved
        ↓
All page results are merged into raw OCR JSON
        ↓
Question analyzer converts OCR blocks into structured questions
        ↓
Validator checks structured questions against the source OCR
        ↓
Word, Excel and validation JSON files are generated
        ↓
Browser displays download buttons
```

## 2. Main components

| Component | Main file | Input | Output |
|---|---|---|---|
| Browser interface | `code/surya_lan_server.py` (`PAGE`) | User actions | HTTP requests |
| HTTP server | `code/surya_lan_server.py` (`Handler`) | HTTP requests | Saved upload, status, downloads |
| Job queue | `code/surya_lan_server.py` (`QUEUE`, `worker`) | Job ID | One running OCR process at a time |
| OCR pipeline | `code/run_surya.py` | PDF | OCR page cache, combined JSON and text |
| Question analyzer | `code/paper_analyzer.py` | OCR JSON | `Analysis` object |
| Structure rules | `code/question_structure.py` | Question text and context | Question-type decisions |
| Validation | `code/question_validation.py` | `Analysis` | Checked records and report |
| Word exporter | `code/export_documents.py` | OCR pages | `.docx` |
| Excel exporter | `code/dynamic_excel.py` | Validated questions | `.xlsx` |
| Math handling | `code/word_math.py`, `code/excel_math.py` | OCR math | Word equations/readable Unicode |

## 3. Essential technical definitions

### Client

The browser used by the person operating Mintbook OCR. It displays HTML and JavaScript and sends requests to the server.

### Server

The Python program listening on port `8502`. It receives uploads, creates jobs, reports progress, and sends output files.

### HTTP request

A message sent from the browser to the server. This project uses:

- `GET /` to load the interface;
- `POST /api/jobs` to upload a PDF;
- `GET /api/jobs/{job_id}` to read progress;
- `GET /api/jobs/{job_id}/files/{filename}` to download a result.

### API endpoint

A server path that performs a specific operation. For example, `/api/jobs` creates a processing job.

### Process

An independently running program. The web server starts separate Python processes for OCR and export using `subprocess.Popen`.

### Thread

A path of execution inside one process. The server uses a background worker thread, and the OCR watchdog uses threads to enforce time limits.

### Queue

A first-in, first-out collection. Uploaded jobs wait in `QUEUE`; the worker processes them one at a time.

### OCR

Optical Character Recognition. It converts page images into editable text and layout blocks.

### Layout block

One detected page element such as a heading, paragraph, list, or equation. A block includes text/HTML, position, and reading order.

### JSON

A structured text format. OCR results are stored in JSON because it preserves pages, blocks, coordinates, labels, and text.

### Cache

Saved intermediate results. Per-page OCR JSON allows a command-line run to resume without repeating completed pages.

### Schema

A formal definition of allowed data. Pydantic models define the required shape of questions, options, sources, and analyses.

### Regular expression

A text pattern used to recognize structures such as question numbers, option labels, marks, “fill in the blanks,” and OR/अथवा.

### Atomic write

A safe file-writing technique. The complete new file is prepared before it replaces the target, reducing the chance of a corrupt partial cache file after interruption.

## 4. Starting the application

### Local start

Command:

```powershell
.\start_surya_local.cmd
```

File flow:

```text
start_surya_local.cmd
   ↓
.venv\Scripts\python.exe
   ↓
code\surya_lan_server.py --host 127.0.0.1 --port 8502 --no-token
```

Definitions:

- `.venv` is the project’s isolated Python environment.
- `127.0.0.1` means this computer only.
- `8502` is the TCP port.
- `--no-token` disables URL access tokens for the local-only interface.

### Wi-Fi start

The Wi-Fi launcher ultimately runs the same server with host `0.0.0.0`. That means the server listens on network interfaces, allowing devices on the same permitted network to connect. Token mode can protect the URL.

### Server initialization

Function: `main()` in `code/surya_lan_server.py`.

Logical sequence:

1. Read command-line arguments.
2. Confirm `.venv\Scripts\python.exe` exists.
3. Create `runtime/lan_jobs` if required.
4. Start the background `worker()` thread.
5. Create `ThreadingHTTPServer((host, port), Handler)`.
6. Save the access token on the server object.
7. Print the URL.
8. Call `serve_forever()` to wait for browser requests.

## 5. Loading the Mintbook OCR page

The browser requests:

```http
GET /
```

`Handler.do_GET()` checks the requested path and token. If valid, it returns the `PAGE` string as HTML.

The `PAGE` value contains:

- HTML: page structure;
- CSS: colors, spacing, buttons and progress display;
- JavaScript: upload, status polling and download behavior.

The browser receives HTML bytes and renders the interface. No PDF processing happens at this stage.

## 6. Selecting one PDF or a folder of PDFs

The interface provides two modes:

- **One PDF** uses an ordinary file input;
- **PDF folder** uses a folder input with multiple-file support.

Simplified HTML:

```html
<input id="singlePdf" type="file" accept="application/pdf,.pdf">
<input id="pdfFolder" type="file" accept="application/pdf,.pdf"
       webkitdirectory multiple>
```

`webkitdirectory` instructs a supported browser to return files from a selected folder. `multiple` allows the input to contain more than one file. JavaScript still filters the returned list by the `.pdf` extension because browser file filters are guidance rather than a security boundary.

Function: `selectedPdfs()` inside the `PAGE` JavaScript in `code/surya_lan_server.py`.

It:

1. reads the selected upload mode;
2. chooses the single-file or folder input;
3. converts the browser `FileList` into a JavaScript array;
4. keeps only names ending in `.pdf`;
5. sorts the PDFs using their relative folder paths and filenames.

Nested folder PDFs are included because the browser supplies `webkitRelativePath` for folder selections.

### Selecting the output folder

Clicking **Browse folder** calls:

```javascript
outputDirectory = await window.showDirectoryPicker({mode: "readwrite"});
```

This is the browser File System Access API. It returns a directory handle after the user grants permission.

The application deliberately does not accept a typed value such as `C:\Output`. A website cannot safely write to an arbitrary operating-system path. The picker gives access only to the directory approved by the user.

Requirements:

- current Microsoft Edge or Google Chrome;
- `localhost` for local operation or HTTPS for a deployed service;
- explicit user permission through the picker.

### Starting a single-file or batch run

When the user clicks **Create Word and Excel**, the form handler calls `selectedPdfs()`. It requires at least one PDF and an approved output directory.

It then uses a sequential loop:

```javascript
for (let i = 0; i < files.length; i++) {
    // upload current PDF
    // wait for its server job
    // save every generated output
}
```

For each file, JavaScript creates a fresh `FormData` value:

```javascript
const form = new FormData();
form.append("pdf", files[i], files[i].name);
```

It sends that one PDF to the existing endpoint:

```javascript
fetch('/api/jobs?token=' + encodeURIComponent(token), {
    method: 'POST',
    body: form
})
```

### Logical meaning

1. Build the ordered list of selected PDFs.
2. Upload the current PDF to `/api/jobs`.
3. Receive its job ID.
4. Call `waitForJob()` until that job completes or fails.
5. Call `saveOutput()` for each returned Word, Excel and analysis file.
6. Continue with the next PDF.
7. Display the final processed-file count.

The server still receives one PDF per request. Batch orchestration stays in the browser and reuses the existing tested single-document server pipeline.

### Why processing is sequential

OCR can consume substantial GPU memory, RAM and CPU. Sequential processing prevents several models from competing for the same machine resources. It also makes progress and failure reporting clear: `PDF 2 of 10`, for example.

### Saving each generated output

Function: `saveOutput(jobId, name)`.

It downloads one completed file from the existing job-scoped endpoint, creates or opens the same filename inside the approved output directory, writes the response blob and closes the writable stream:

```javascript
const handle = await outputDirectory.getFileHandle(name, {create: true});
const writable = await handle.createWritable();
await writable.write(await response.blob());
await writable.close();
```

The browser saves each output immediately after its PDF completes. If a later PDF fails, files from earlier successful PDFs remain in the selected directory.

The current batch stops on the first failed PDF and displays its error. This avoids silently skipping a document while presenting the batch as successful.

### Server-side upload handling

Function: `Handler.do_POST()` in `code/surya_lan_server.py`.

The server performs these checks:

1. The path must be `/api/jobs`.
2. The URL token must be valid when token protection is enabled.
3. `Content-Length` must be positive and at most 200 MB.
4. The request must be `multipart/form-data`.
5. A field named `pdf` must exist.
6. The file bytes must begin with `%PDF-`.

`multipart/form-data` is the HTTP format used to send files and ordinary form fields in one request.

### Safe filename

Function: `safe_pdf_name()`.

It:

- removes directory paths supplied by the browser;
- replaces unsafe characters;
- forces a `.pdf` extension.

This stops an uploaded filename from writing outside the intended job folder.

### Job ID creation

```python
job_id = secrets.token_hex(8)
```

This creates a random 16-character hexadecimal identifier, for example:

```text
9f46a7db13c1228e
```

## 7. Exact upload storage location

For a job ID of `9f46a7db13c1228e` and a file named `HOME SCIENCE.pdf`, the server creates:

```text
runtime/
└── lan_jobs/
    └── 9f46a7db13c1228e/
        ├── input/
        │   └── HOME SCIENCE.pdf
        └── output/
```

Code variables:

```text
job_dir   = runtime/lan_jobs/{job_id}
input_dir = runtime/lan_jobs/{job_id}/input
output_dir= runtime/lan_jobs/{job_id}/output
pdf_path  = runtime/lan_jobs/{job_id}/input/{safe_filename}
```

The bytes received from the browser are written to `pdf_path`.

## 8. Creating and queuing the job

The server stores an in-memory dictionary containing:

```text
id, filename, state, message, log, outputs,
progress_current, progress_total, progress_percent,
active_page, page_status, pdf_path, output_dir,
dense_recovery, created_at, started_at, updated_at
```

It stores the dictionary in:

```python
JOBS[job_id] = job
```

Then it queues the ID:

```python
QUEUE.put(job_id)
```

Finally, it returns HTTP status `202 Accepted` and the job ID to the browser.

`202` means the request was accepted but processing continues asynchronously.

### Why only the ID goes into the queue

The full job data remains in `JOBS`. Passing only the ID keeps the queue small and gives the worker one authoritative place to read and update state.

### Why `LOCK` exists

Browser request threads and the worker can access `JOBS` simultaneously. `threading.RLock()` prevents them from changing shared job data at the same moment.

## 9. Browser status polling

After upload, JavaScript calls:

```http
GET /api/jobs/{job_id}
```

approximately every two seconds while the job is active.

`Handler.do_GET()` reads the job under `LOCK`, calls `public_job()`, and returns safe status fields as JSON.

The browser updates:

- the main status message;
- percentage bar;
- current/completed pages;
- elapsed time;
- processing details;
- download links when complete.

Polling was chosen because it is simple and reliable for a local application. The browser repeatedly asks for the newest state instead of keeping a permanent streaming connection.

## 10. Worker receives the job

Function: `worker()` in `code/surya_lan_server.py`.

The worker runs an infinite loop:

```python
while True:
    job_id = QUEUE.get()
```

It changes the job state from `queued` to `ocr`, then builds this subprocess command:

```powershell
.venv\Scripts\python.exe -u code\run_surya.py "{uploaded_pdf}" --force
```

If **Improve difficult pages** is selected, it adds:

```text
--dense-page-policy recover
```

### Why a subprocess is used

OCR has its own model, backend, memory, logs, retries, and exit code. Running it as a subprocess isolates that lifecycle from the web server. A failed OCR process does not directly terminate the server.

### Meaning of `-u`

Unbuffered Python output. Progress lines are sent immediately so the UI can update while OCR runs.

### Meaning of `--force` in the web workflow

The current browser workflow intentionally reprocesses the uploaded PDF for a fresh run. The command-line workflow can omit `--force` and reuse valid cached pages.

## 11. Capturing subprocess progress

Function: `run_command()`.

It uses `subprocess.Popen` with:

- working directory set to the project root;
- standard error redirected into standard output;
- UTF-8 text mode;
- line buffering.

Every output line goes to `add_log()`.

`add_log()` recognizes patterns such as:

```text
Pages selected: 4
Page 2/4 [##########----------] 50.0% | ...
Page 2: sending full page to OCR backend
PIPELINE_STAGE: analyzing
```

It converts those lines into structured UI state.

## 12. OCR program initialization

File: `code/run_surya.py`.

Function: `main()`.

It validates arguments, including:

- inference request timeout;
- full-page hard timeout;
- recovery-region timeout;
- retry counts;
- token limits;
- split depth;
- split-part count;
- page range.

It then calls `configure_bounded_inference()`.

### Inference configuration

The application uses Surya’s recognition model with a local inference backend.

`configure_bounded_inference()`:

- sets inference timeout;
- limits retries;
- disables guided layout grammar because the local llama.cpp build rejects it on some fallback pages;
- installs Windows-safe process stopping;
- preserves Surya’s normal JSON validation after inference.

### CPU/GPU selection

`code/run_surya.py` checks whether the configured GPU backend is available.

Possible modes:

- **CUDA partial offload:** selected model layers run on the GPU, with remaining work/system work on CPU;
- **CPU fallback:** inference runs without GPU offload.

PDF loading, orchestration, parsing, validation, Word generation, and Excel generation still mainly use CPU even when OCR inference uses GPU.

## 13. Opening the PDF and selecting pages

`PdfDocument` from `pypdfium2` opens the PDF and reads the total page count.

The application calculates the requested zero-based indexes:

```text
start = first selected index, default 0
end   = last selected index, default last PDF page
indexes = [start, start+1, ..., end]
```

Invalid ranges stop before model loading.

## 14. PDF fingerprint and cache

Function: `pdf_fingerprint()` calculates a SHA-256 identity using the PDF.

Purpose:

- distinguish files even when their names match;
- associate page cache entries with the correct source document.

The cache is under:

```text
output/surya_pages/{document-specific-cache}/
```

Typical contents:

```text
manifest.json
run_status.json
page_0001.json
page_0002.json
page_0003.error.json
```

`manifest.json` stores the PDF path, SHA-256 fingerprint, and total pages.

`valid_cached_page()` accepts a page only if it is valid JSON, contains a block list, and has the expected `source_page_index`.

## 15. Loading Surya OCR

The model client is created lazily:

```python
predictor = RecognitionPredictor(SuryaInferenceManager())
```

“Lazily” means it is created only when a page actually needs OCR. A fully cached command-line run does not need to initialize the model.

## 16. Normal processing of one page

Main functions:

- `recognize_with_deadline()`
- `recognize_page()`
- `validate_page_result()`

### Step 1: Render the page

```python
load_pdf(str(pdf), page_range=[page_index])
```

This converts the selected PDF page to an image.

### Step 2: Profile the page

`profile_page_image()` calculates:

- image width and height;
- source pixel count;
- dark-pixel ratio;
- whether the page is blank;
- a normal/dense risk label.

The profile does not rewrite recognized text. It supports logging and optional recovery decisions.

### Step 3: Skip a genuinely blank page

If Surya’s blank-region check says the page is blank, model inference is skipped and a valid empty page result is returned.

### Step 4: Full-page inference

```python
predictor([image], full_page=True)
```

The output is converted to a Python dictionary with `model_dump()` and receives `source_page_index`.

### Step 5: Hard watchdog

`recognize_with_deadline()` runs page recognition inside a daemon thread. It waits up to the configured hard timeout and prints heartbeat messages.

If the thread remains stuck:

1. the page is declared stalled;
2. `stop_stalled_local_backend()` stops the registered local llama.cpp process;
3. the code verifies the Windows PID belongs to `llama-server.exe` before killing it;
4. a fresh backend client is created for recovery.

PID verification prevents a stale process ID from terminating an unrelated program.

## 17. Page-result validation

`validate_page_result()` checks:

- a non-blank page returned a block list;
- at least one block exists;
- recognized blocks contain visible text;
- when difficult-page recovery is enabled, a dense page has enough visible characters.

The optional dense-character check is conservative and only applies in recovery mode.

## 18. Adaptive split recovery

If full-page OCR fails, stalls, or fails validation, the page moves to `recognize_split_adaptive()`.

Workflow:

1. Load the page image.
2. Divide it into overlapping horizontal regions.
3. Send each region separately to OCR.
4. Give each region its own timeout and smaller token cap.
5. If one region fails, divide only that region into two overlapping child regions.
6. Repeat until success or maximum split depth.
7. Move crop coordinates back into original page coordinates.
8. Combine all blocks.
9. Remove duplicate blocks created by overlaps.

### Why overlap is used

Without overlap, a line exactly at a crop boundary could be cut in half. Overlap allows both regions to see boundary content.

### Why de-duplication is required

Overlap can recognize the same line twice. `deduplicate_overlap_blocks()` normalizes block text and compares nearby vertical coordinates before removing a copy.

### Why only the failed region is subdivided

Successful regions are kept. Reprocessing the whole page would waste time and could introduce different OCR results in already successful areas.

## 19. Saving one page safely

After validation passes:

```text
output/surya_pages/.../page_XXXX.json
```

is written using `atomic_text()`.

If the page ultimately fails, an error file is written instead:

```text
page_XXXX.error.json
```

The loop then reports failure and can continue. At the end, final merging succeeds only if every selected page has valid cache data.

## 20. Merging pages into raw OCR output

Function: `merge_pages()`.

It loads cached pages in requested order and creates:

```text
output/surya/{pdf_stem}_surya.json
output/surya/{pdf_stem}_surya.txt
```

The JSON is the structured source of truth. The text file is a readable inspection copy.

Simplified JSON structure:

```json
[
  {
    "source_page_index": 0,
    "image_bbox": [0, 0, 1600, 2200],
    "blocks": [
      {
        "label": "Text",
        "html": "1. What is ...?",
        "bbox": [100, 250, 900, 320],
        "reading_order": 4
      }
    ]
  }
]
```

## 21. Returning from OCR to the web worker

The OCR subprocess returns exit code:

- `0`: OCR output is complete;
- non-zero: the web job becomes failed.

The web worker expects:

```text
output/surya/{uploaded_filename_without_extension}_surya.json
```

If it exists, the worker starts the export subprocess:

```powershell
.venv\Scripts\python.exe -u code\export_documents.py \
  "output\surya\{name}_surya.json" \
  --destination "runtime\lan_jobs\{job_id}\output"
```

## 22. Loading OCR JSON for export

File: `code/export_documents.py`.

Function: `main()`.

Sequence:

1. Read the OCR JSON into `pages`.
2. Convert pages to source blocks.
3. Run question analysis in the selected mode; default is rules.
4. Validate the analysis.
5. Save structured analysis JSON.
6. Save validation/report JSON.
7. Build Word.
8. Build Excel.

The exporter prints `PIPELINE_STAGE` messages. The web server translates them into user-facing states such as analyzing, validating, and exporting.

## 23. Converting OCR blocks to source records

Function: `source_blocks()` in `code/paper_analyzer.py`.

For every page:

1. Sort blocks by `reading_order`.
2. Parse block HTML with BeautifulSoup.
3. Preserve ordered-list numbering.
4. Create logical text lines.
5. Assign a stable source ID such as `p2b5`.

`p2b5` means page 2, block 5 in the analyzed order.

Each `SourceBlock` stores:

```text
id, page, label, text
```

## 24. Structured question schema

File: `code/question_schema.py`.

One `QuestionRecord` contains:

```text
number         question number
section        surrounding section/title
kind           mcq, fill_blank, matching, etc.
text           language → question text
options        list of labelled multilingual options
marks          numeric marks when evidenced
marks_evidence exact source string supporting marks
source_ids     OCR blocks supporting this record
review         detected uncertainty/problems
```

Pydantic uses `extra="forbid"`, which means unexpected fields cause validation failure rather than being silently accepted.

## 25. Dynamic question detection

Main function: `analyze_rules()` in `code/paper_analyzer.py`.

Supporting rules: `code/question_structure.py`.

### Logical sequence

1. Convert OCR blocks to ordered logical lines.
2. Ignore known page headers, footers, pictures, and skipped blocks.
3. Identify instruction/front-matter lines.
4. Detect section headings as context.
5. Detect question-number patterns.
6. Determine each question’s type from its own wording and structure.
7. Read ahead for option evidence.
8. Separate option labels and values.
9. Join translations of the same numbered question.
10. Attach subparts to the parent question.
11. Attach OR/अथवा alternatives to the parent question.
12. Capture marks only from supported evidence.
13. Preserve every original source block even when it cannot be classified.

### Question-number patterns

Supported examples include:

```text
1. Question
1) Question
Q12: Question
2(a): Question
IV. Question
1.10 Question
```

### Option patterns

Supported examples include:

```text
(A) Delhi
A. Delhi
(a) Delhi
(1) Delhi
(क) दिल्ली
(ক) ...
```

The parser requires meaningful choice evidence so mathematical parentheses or ordinary numbered statements are not automatically treated as options.

### Per-question type detection

Examples:

| Evidence | Detected kind |
|---|---|
| Multiple-choice wording or two or more labelled alternatives | `mcq` |
| “Fill in the blanks”, “रिक्त स्थान” | `fill_blank` |
| “True or False”, “सत्य/असत्य” | `true_false` |
| “Match the following”, “मिलान” | `matching` |
| “Short answer”, “लघु उत्तरीय” | `short_answer` |
| “Long answer”, essay, “दीर्घ उत्तरीय” | `long_answer` |
| explain, describe, discuss, write, draw, etc. | `descriptive` |

Explicit evidence inside a question takes priority over the surrounding section type. This is why different question patterns can exist within the same section.

### Bilingual questions

`language_text()` detects supported Unicode scripts. If the same question number appears in another language and does not conflict with existing language content, it is joined into the same record.

The system preserves text. It does not translate it.

### OR/अथवा

A standalone `OR`, `अथवा`, or `या` is appended to the current question. A repeated question number following that marker is treated as the alternative for the same parent record.

### Composite patterns

Fill blanks, matching, and true/false may contain several subitems. Those subitems stay within the parent question until a new top-level question or explicit section begins.

### Multiline short- and long-answer blocks

Some OCR results place many questions into one `ListGroup`, for example questions 1–10 in a single block. Testing the entire multiline block against a single-question expression would fail because additional lines follow the first question.

The analyzer therefore:

1. finds the first non-empty logical line in the block;
2. checks whether that line begins with a valid question number;
3. ends instruction-skipping mode when the current section is a known question section;
4. splits the block into its numbered questions;
5. attaches following unnumbered translation lines to the current question;
6. preserves an inherited `short_answer` or `long_answer` category for verbs such as “explain”, “define” and “discuss”.

A general front-page sentence that merely describes future sections does not establish persistent question type. Only actual section context is inherited. This prevents a sentence such as “Section B contains short-answer questions” from incorrectly classifying unrelated content later in the document.

## 26. Optional AI analysis

Default mode is rules. Optional AI mode uses `code/model_client.py`.

AI mode:

1. Sends selected source blocks to a configured OpenAI-compatible endpoint.
2. Requires a JSON schema generated from Pydantic models.
3. Uses temperature `0`.
4. Validates the response against the schema.
5. Checks source references.
6. Falls back to rule analysis on error or invalid output.

Remote use is blocked unless explicitly allowed, and a remote endpoint must use HTTPS.

## 27. Validation workflow

Function: `validate_analysis()` in `code/question_validation.py`.

For every question, validation checks:

- source IDs exist;
- question text is non-empty;
- text and options appear in linked source evidence;
- question type is known;
- MCQs have at least two non-empty choices;
- option labels are unique;
- repeated question numbers are retained and flagged;
- marks have explicit evidence in the OCR source.

Validation follows an evidence-first policy. Unsupported marks are removed rather than guessed.

`validation_report()` produces document-level counts and review details as JSON.

## 28. Word generation

Function: `build_word()` in `code/export_documents.py`.

Input: raw OCR pages.

Logical sequence:

1. Create a new `python-docx` document.
2. Configure page margins.
3. Add the document title.
4. Iterate pages and blocks in reading order.
5. Skip page headers, page footers, pictures, and explicitly skipped blocks.
6. Convert HTML blocks to logical lines.
7. Remove recognized duplicate blocks.
8. Remove standalone margin-mark numbers when the paper states marks are printed in the margin.
9. Apply heading, question, option, and subpart formatting.
10. Convert supported math to native Word equations.
11. Add page breaks between OCR pages.
12. Save `.docx`.

Word follows the readable source flow. Excel uses structured question records.

## 29. Equation processing

`code/structured_output.py` preserves math expressions using temporary markers while ordinary text is arranged.

`code/word_math.py` performs:

```text
LaTeX
  ↓ latex2mathml
MathML
  ↓ mathml2omml
Word OMML equation
```

OMML is Microsoft Word’s native equation XML format.

If conversion fails, `code/excel_math.py` produces readable Unicode where possible, and original recognized content is retained.

## 30. Dynamic Excel generation

Function: `build_dynamic_excel()` in `code/dynamic_excel.py`.

Input: validated `Analysis`.

Sequence:

1. Create a workbook.
2. Add a cover page.
3. Group questions by `question.kind`.
4. Detect languages actually present in each group.
5. Detect option labels actually present.
6. Create one sheet per question type present.
7. Create dynamic headers.
8. Add question records.
9. Apply styling, wrapping, row height and column widths.
10. Configure printing.
11. Save `.xlsx`.

Examples:

- MCQ sheets receive question, option, marks and answer columns.
- Fill-blank and true/false questions receive their own sheets.
- Matching receives Question/Instruction, Column A, Column B, Marks and Answer.
- OR/अथवा remains within the parent question row.

OCR/model text is forced to Excel text type. A recognized string beginning with `=` therefore cannot become an executable Excel formula.

## 31. Final job output location

For job `9f46a7db13c1228e`:

```text
runtime/lan_jobs/9f46a7db13c1228e/output/
├── HOME SCIENCE.docx
├── HOME SCIENCE.xlsx
└── HOME SCIENCE_analysis.json
```

The validation summary is written separately to:

```text
reports/evaluation/HOME SCIENCE_structure.json
```

The browser lists `.docx`, `.xlsx`, and `.json` files found in the job output directory. The internal validation report remains under `reports/evaluation`.

## 32. Completing the job

When export returns exit code `0`, the worker:

1. scans the job output folder;
2. records allowed filenames;
3. sets `state="completed"`;
4. sets the message “Your Word and Excel files are ready.”

The next browser poll receives the completed state and filenames.

## 33. Downloading files

The browser creates links such as:

```http
GET /api/jobs/{job_id}/files/HOME%20SCIENCE.xlsx
```

Before returning a file, `Handler.do_GET()` checks:

- the job exists;
- the requested name is reduced to a basename;
- the filename appears in that job’s allowed output list;
- the file exists inside that job’s output folder.

The server assigns the correct MIME type and sends it as an attachment.

## 34. Failure paths

### Upload failure

Examples: missing PDF, invalid `%PDF-` signature, oversized upload, invalid form encoding. The server returns an HTTP error and does not queue a job.

### OCR page failure

The code retries according to configuration, creates a fresh backend after relevant failures, attempts adaptive split recovery, records an error file, and continues where possible.

### Incomplete document

If any selected page lacks valid cached JSON, `merge_pages()` refuses to produce a falsely complete final result. OCR exits non-zero.

### Export failure

If the export subprocess exits non-zero or creates no outputs, the job becomes `failed` and the UI displays the error.

### Browser interruption

Closing the browser does not stop the worker. The server continues processing. Reopening the exact active URL can access server state while that server process remains running.

### Server interruption

In-memory `JOBS` and queue state are lost when the server process stops. Saved PDF, page cache, raw OCR and completed output files remain on disk.

## 35. End-to-end example

Assume the user uploads `History 2014.pdf`.

```text
1. Browser POSTs History 2014.pdf to /api/jobs.
2. Server validates it and creates job ID a1b2c3d4e5f60718.
3. PDF is saved at:
   runtime/lan_jobs/a1b2c3d4e5f60718/input/History 2014.pdf
4. Job ID enters QUEUE.
5. worker() starts code/run_surya.py with that PDF.
6. run_surya.py fingerprints the PDF and creates a page-cache folder.
7. Each page is rendered and sent to Surya OCR.
8. Failed/stalled pages use adaptive split recovery.
9. Valid page JSON is written atomically to output/surya_pages/...
10. Page JSON is merged into:
    output/surya/History 2014_surya.json
11. worker() starts code/export_documents.py.
12. paper_analyzer.py detects questions, languages, options, types, marks and alternatives.
13. question_validation.py checks evidence.
14. export_documents.py creates Word.
15. dynamic_excel.py creates Excel sheets.
16. Outputs are saved under:
    runtime/lan_jobs/a1b2c3d4e5f60718/output/
17. Job state becomes completed.
18. Browser polling receives output filenames.
19. User clicks Download Word or Download Excel.
20. Server validates the file request and returns the file.
```

## 36. Function call map

```text
start_surya_local.cmd
└── surya_lan_server.main()
    ├── starts worker() thread
    └── ThreadingHTTPServer.serve_forever()
        ├── Handler.do_GET()
        │   ├── returns PAGE
        │   ├── returns public_job()
        │   └── returns output file
        └── Handler.do_POST()
            ├── safe_pdf_name()
            ├── writes uploaded PDF
            ├── JOBS[job_id] = job
            └── QUEUE.put(job_id)

worker()
├── run_command(run_surya.py)
│   └── run_surya.main()
│       ├── configure_bounded_inference()
│       ├── pdf_fingerprint()
│       ├── valid_cached_page()
│       ├── RecognitionPredictor(...)
│       ├── recognize_with_deadline()
│       │   └── recognize_page()
│       ├── validate_page_result()
│       ├── recognize_split_adaptive() on failure
│       ├── atomic_text(page cache)
│       └── merge_pages()
└── run_command(export_documents.py)
    └── export_documents.main()
        ├── analyze_paper()
        │   ├── source_blocks()
        │   ├── analyze_rules()
        │   └── optional ModelClient
        ├── validate_analysis()
        ├── write_validation()
        ├── build_word()
        │   └── WordMathRenderer
        └── build_excel()
            └── build_dynamic_excel()
```

## 37. Logical design decisions

### Why raw OCR and structured analysis are separate

OCR answers “what text/layout is visible?” Analysis answers “which text belongs to which question?” Keeping them separate makes parsing improvements possible without rerunning OCR.

### Why Word and Excel use different representations

Word is intended to preserve readable document flow. Excel is intended to organize question records into columns and sheets. One representation cannot serve both purposes well.

### Why rules are the default

Rules are local, repeatable, testable, and evidence-based. They do not require network access and are less likely to invent missing content.

### Why the original OCR JSON is preserved

It allows auditing, parser improvements, re-exporting, and comparison with the source without repeating expensive OCR.

### Why one OCR job runs at a time

OCR models consume substantial RAM, GPU memory and CPU. A single worker protects the machine while still allowing multiple users to queue jobs.

### Why uncertain matching content is not guessed

Putting a left-column item into the wrong right column changes meaning. When structural evidence is missing, preserving raw text is safer than manufacturing a pair.

## 38. What is dynamic and what remains configured

Dynamic behavior:

- question numbers;
- number of questions;
- detected languages;
- option count and labels;
- question types per question;
- sheets created;
- matching columns;
- row heights and relevant columns.

Configured behavior:

- port `8502` by default;
- maximum upload 200 MB;
- OCR timeouts and token limits;
- one worker queue;
- supported question-type evidence patterns;
- output styling;
- permitted output extensions.

Dynamic does not mean “no rules.” It means the rules respond to actual evidence rather than one fixed PDF template.

## 39. Files to study with this workflow

Read these sections beside the code:

1. Startup and upload: `code/surya_lan_server.py`
2. Page processing: `code/run_surya.py`
3. Records: `code/question_schema.py`
4. Structural rules: `code/question_structure.py`
5. Parsing: `code/paper_analyzer.py`
6. Evidence checks: `code/question_validation.py`
7. Export orchestration: `code/export_documents.py`
8. Excel: `code/dynamic_excel.py`
9. Word math: `code/word_math.py`
10. Proven behavior: `tests/`

The current regression suite contains **50 passing automated tests**. It includes cases for packed short/long questions, per-question classification, bilingual questions, OR/अथवा, matching columns, formula safety, Word margin-mark cleanup, OCR recovery, UI status and folder-based batch processing.

The corpus audit covers **762 PDFs and 13,873 pages**: **642 unique files** and **120 exact duplicates**. These figures describe automated inventory and pattern testing, not a manual guarantee for every page.

## 40. Deployment boundary

The current server uses Python’s standard `ThreadingHTTPServer`. It is designed for local operation and controlled pilot testing.

Before exposing Mintbook OCR as a public customer service, the architecture requires:

- a production web API/ASGI server;
- customer authentication and authorization;
- persistent job and user records;
- a durable queue;
- private object storage;
- isolated OCR workers;
- HTTPS and secure secrets management;
- upload security, quotas and rate limits;
- monitoring, backups and retention/deletion policies.

The browser folder picker remains suitable for a future internet service when delivered over HTTPS, but the current local HTTP server itself must not be exposed directly to the public internet.

## 41. One-minute technical explanation

“The browser uploads a PDF through an HTTP multipart request to our Python server. The server validates the PDF, stores it in an isolated job directory, adds its ID to a single-worker queue, and starts the OCR pipeline as a subprocess. The OCR program fingerprints the PDF, renders pages with PDFium, runs Surya recognition through the configured local inference backend, validates each page, and saves atomic page-level JSON. Failed or stalled pages use overlapping adaptive region recovery. Completed pages are merged into raw OCR JSON. The exporter then converts OCR blocks into source-linked Pydantic question records, classifies every question independently using structural rules, validates text and marks against source evidence, and generates a readable Word document plus dynamically grouped Excel sheets. The web server parses subprocess progress, the browser polls job status, and completed files are downloaded through job-scoped endpoints.”
