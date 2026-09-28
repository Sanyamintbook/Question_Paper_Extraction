# PDF corpus pattern test summary

## Corpus audit

- Source folder: `H_Downloads/Q&A PDF`
- PDF files: 762
- Exact unique files: 642
- Exact duplicate copies: 120
- Pages in unique files: 13,873
- Image-only or sparse-text PDFs: 617
- PDFs unreadable by PDFium: 25

All files were inventoried and hashed. The corpus is almost entirely scanned
images, so structural patterns cannot be extracted reliably from PDF text.
Representative pages were visually reviewed across 2014-2023, grades 10/12,
major subjects, and Bengali/Hindi/English papers.

## Patterns represented in tests

1. Numbered front-matter instructions that resemble questions.
2. OMR objective sections containing 2-5 options and 35-100 questions.
3. Bilingual questions where the translated question has no repeated number.
4. Bengali and Devanagari option labels.
5. Section and group names, including Section-A/Section-B and Group A-E.
6. Short-answer and long-answer transitions within the same broad section.
7. Fill-in-the-blank tasks with Roman-numbered subparts in one parent question.
8. Passage/case material followed by Roman or lettered subquestions.
9. OR/अथवा alternatives that belong to one numbered question.
10. Standalone and trailing marks, explicit mark phrases, and word limits.
11. Mathematics expressions, decimals, diagrams, and numeric choices.
12. Papers where the same structure is split into one OCR block or many blocks.

## Verification

- Unit/integration regression suite: 50 tests.
- Saved OCR structural audit: `saved_ocr_validation.json`.
- Full PDF inventory: `pdf_pattern_audit.json`.

The rules are structure-based and do not use fixed subjects or question numbers.
This audit does not claim perfect accuracy over all 13,873 scanned pages: only a
full OCR run plus comparison against answer keys could establish that. The audit
does establish corpus coverage, duplicate counts, representative layout review,
parser stability on saved OCR, and regression coverage for the observed patterns.
