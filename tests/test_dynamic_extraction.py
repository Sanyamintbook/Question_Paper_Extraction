import json
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from openpyxl import load_workbook
from paper_analyzer import analyze_paper, analyze_rules
from question_schema import Extraction, PaperPlan, QuestionRecord
from question_validation import validate_analysis, review_rows
from dynamic_excel import build_dynamic_excel
from model_client import ModelClient


def pages(*texts, heading=None):
    blocks = ([{"label": "Text", "html": heading}] if heading else [])
    blocks += [{"label": "Text", "html": text} for text in texts]
    for index, block in enumerate(blocks):
        block["reading_order"] = index
    return [{"source_page_index": 0, "blocks": blocks}]


class DynamicTests(unittest.TestCase):
    def test_corpus_front_matter_ranges_and_standalone_marks(self):
        p = pages('General Instructions:',
                  '5. This question booklet is divided into two sections - Section-A and Section-B.',
                  '6. In Section-A, there are 100 objective type questions, each carrying 1 mark.',
                  '7. In Section-B, there are 20 short answer questions and 6 long answer questions.',
                  '8. Use of any electronic appliances is strictly prohibited.',
                  '1. Which value is correct?', '(A) One', '(B) Two', '(1)',
                  '2. Explain the process.', '(2)')
        a = validate_analysis(analyze_rules(p))
        self.assertEqual([q.number for q in a.questions], ['1','2'])
        self.assertEqual(a.questions[0].kind, 'mcq')
        self.assertEqual(a.questions[0].marks, 1)
        self.assertEqual(a.questions[1].kind, 'descriptive')
        self.assertEqual(a.questions[1].marks, 2)

    def test_packed_short_and_long_questions_after_same_page_instructions(self):
        p = pages("Short Answer Type Questions.",
                  "Question Nos. 1 to 30 are short answer type. Answer any 15 questions. Each question carries 2 marks.",
                  "1. सकल राष्ट्रीय उत्पाद क्या होता है ? 2\nWhat is Gross National Product ?\n"
                  "2. ऑपरेशन फ्लड से क्या अभिप्राय है ? 2\nWhat is meant by operation flood ?")
        p[0]["blocks"] += [
            {"label": "SectionHeader", "html": "Long Answer Type Questions", "reading_order": 3},
            {"label": "Text", "html": "Question Nos. 31 to 38 are Long answer type. Answer any 4 questions. Each question carries 5 marks.", "reading_order": 4},
            {"label": "ListGroup", "html": "31. भारत के केन्द्रीय बैंक के कार्यों की व्याख्या करें। 5<br>Explain the functions of the central bank.<br>32. कर को परिभाषित करें। 5<br>Define tax.", "reading_order": 5},
        ]
        result = analyze_rules(p)
        self.assertEqual([q.number for q in result.questions], ["1", "2", "31", "32"])
        self.assertEqual([q.kind for q in result.questions],
                         ["short_answer", "short_answer", "long_answer", "long_answer"])
        self.assertIn("Gross National Product", result.questions[0].english)
        self.assertIn("Define tax", result.questions[3].english)

    def test_passage_and_roman_subparts_stay_in_one_question(self):
        a = analyze_rules(pages('SECTION A', '1. Read the passage and answer:',
                                'A passage paragraph.', 'i) First question?',
                                'ii) Second question?', '2. Write an essay.'))
        self.assertEqual([q.number for q in a.questions], ['1','2'])
        self.assertIn('i) First question?', a.questions[0].english)
        self.assertIn('ii) Second question?', a.questions[0].english)
    def test_roman_top_level_and_repeated_number_alternative(self):
        result = analyze_rules(pages('IV. Explain gravity.', 'V. Explain friction.'))
        self.assertEqual([q.number for q in result.questions], ['IV','V'])
        result = analyze_rules(pages('27. Explain gravity.', 'OR', '27. Describe friction.', '28. Define motion.'))
        self.assertEqual([q.number for q in result.questions], ['27','28'])
        self.assertIn('Describe friction.',result.questions[0].english)
    def test_structure_is_independent_of_question_numbers_and_block_packing(self):
        for first in (2, 37, 108):
            texts = [f'{first}. What is the colour?', 'Some context.', 'More context.',
                     'Additional context.', 'Final context.', '(a) Red', '(b) Blue',
                     f'{first+1}. Match the following:', '(i) Apple — fruit', '(ii) Carrot — vegetable',
                     f'{first+2}. Explain both parts:', '(a) Describe the cause.', '(b) Discuss the effect.',
                     f'{first+3}. Fill in the blanks:', '(i) Water is .....', '(ii) Air is .....',
                     f'{first+4}. Describe the process.']
            for source in (pages(*texts), pages('<br>'.join(texts))):
                result = analyze_rules(source)
                self.assertEqual([q.number for q in result.questions], [str(first+i) for i in range(5)])
                self.assertEqual([q.kind for q in result.questions], ['mcq','matching','descriptive','fill_blank','descriptive'])
                self.assertEqual(len(result.questions[0].options),2)
                for q in result.questions[1:4]:
                    self.assertEqual(q.options,[])
                    self.assertTrue('(ii)' in q.english or '(b)' in q.english)

    def test_composite_question_ends_at_new_section(self):
        p = pages('31. Fill in the blanks:', '(i) Water is .....')
        p[0]['blocks'] += [{'label':'SectionHeader','html':'Section B','reading_order':2},
                           {'label':'Text','html':'32. Explain gravity.','reading_order':3}]
        a=analyze_rules(p)
        self.assertEqual(a.questions[1].kind,'descriptive')
        self.assertNotIn('Section B',a.questions[0].english)

    def test_mixing_colours_is_not_matching_task(self):
        q = analyze_rules(pages('7. रंग मिलाने से क्या बनता है ?', '(क) लाल (ख) नीला')).questions[0]
        self.assertEqual(q.kind, 'mcq')
    def test_bilingual_options_instructions_and_margin_marks(self):
        p = pages("Figures in the right hand margin indicate full marks.",
                  "General Instructions :", "Two alternatives are given for questions 1 to 10. Only one answer is correct.",
                  "1. कौन सा रंग ?", "क) लाल", "ख) नीला", "1", "Which colour ?", "a) Red", "b) Blue",
                  "2. चित्र क्या है ? 4", "What is a picture ?", "Sl. No. 2202", "[ Turn over")
        result = validate_analysis(analyze_rules(p))
        self.assertEqual([q.number for q in result.questions], ["1", "2"])
        mcq, descriptive = result.questions
        self.assertEqual(mcq.kind, "mcq")
        self.assertEqual(mcq.marks, 1)
        self.assertEqual(mcq.options[0].text, {"हिंदी": "लाल", "English": "Red"})
        self.assertEqual(mcq.options[1].text, {"हिंदी": "नीला", "English": "Blue"})
        self.assertEqual(mcq.text, {"हिंदी": "कौन सा रंग ?", "English": "Which colour ?"})
        self.assertEqual(descriptive.kind, "descriptive")
        self.assertEqual(descriptive.marks, 4)
        self.assertEqual(descriptive.english, "What is a picture ?")

    def test_bengali_instructions_parent_number_and_options(self):
        p = pages("Instructions to the candidate :", "1. Write in your own words.")
        p += [{"source_page_index": 1, "blocks": [
            {"html": text, "label": "Text", "reading_order": i}
            for i, text in enumerate(["নির্দেশ :", "ক) নিজের ভাষায় লেখে ।", "1. সঠিক উত্তরটি লেখে :",
                                     "10 \\times 1 = 10", "1.1. কোথায় ?", "(ক) নদীতে (খ) ঘাটে ।",
                                     "1.10. কোন্ ভাষা ?", "(ক) বাংলা (খ) ইংরেজী ।"]) ]}]
        result = analyze_rules(p)
        self.assertEqual([q.number for q in result.questions], ["1.1", "1.10"])
        self.assertTrue(all(q.kind == "mcq" for q in result.questions))
        self.assertEqual(result.questions[0].section, "1. সঠিক উত্তরটি লেখে :")
        self.assertEqual(result.questions[0].options[1].text, {"বাংলা": "ঘাটে ।"})

    def test_heading_free_q_prefix_and_five_options(self):
        result = analyze_rules(pages("Q12: Select one. A. Red B. Blue C. Green D. White E. Black [3 marks]"))
        q = result.questions[0]
        self.assertEqual(q.number, "12")
        self.assertEqual(q.kind, "mcq")
        self.assertEqual([o.label for o in q.options], list("ABCDE"))
        self.assertEqual(q.marks, 3)

    def test_new_heading_and_option_styles(self):
        q = analyze_rules(pages("1) Choose. a) Red b) Blue c) Green", heading="Multiple Choice Questions")).questions[0]
        self.assertEqual(q.section, "Multiple Choice Questions")
        self.assertEqual(len(q.options), 3)

    def test_roman_and_subquestion_numbers(self):
        result = analyze_rules(pages("IV. Explain why.", "Q2(a): Give a reason.", heading="Essay questions"))
        self.assertEqual([q.number for q in result.questions], ["IV", "2(a)"])
        self.assertTrue(all(q.marks is None for q in result.questions))

    def test_unknown_section_does_not_inherit_mcq(self):
        p = pages("1. Select (A) One (B) Two", heading="Objective Type Questions")
        p[0]["blocks"] += [{"label": "SectionHeader", "html": "Experimental Tasks", "reading_order": 2},
                            {"label": "Text", "html": "1. Draw a graph.", "reading_order": 3}]
        q = analyze_rules(p).questions[-1]
        self.assertEqual(q.kind, "descriptive")
        self.assertEqual(q.section, "Experimental Tasks")

    def test_numeric_options_under_mcq_heading(self):
        q = analyze_rules(pages("1. Pick a value", "(1) 10 (2) 20 (3) 30", heading="MCQ")).questions[0]
        self.assertEqual([o.label for o in q.options], ["1", "2", "3"])

    def test_nested_option_references_are_not_new_options(self):
        q = analyze_rules(pages("1. Select (A) One (B) Two (C) Three (D) (B) and (C) both")).questions[0]
        self.assertEqual(q.options[-1].text["English"], "(B) and (C) both")

    def test_cross_page_question_preserves_both_references(self):
        p = pages("1. Explain the process")
        p += [{"source_page_index": 1, "blocks": [{"label": "Text", "html": "and give examples. [4 marks]"}]}]
        q = analyze_rules(p).questions[0]
        self.assertEqual(len(q.source_ids), 2)
        self.assertEqual(q.marks, 4)

    def test_matching_true_false_and_fill_blanks(self):
        for heading, kind in [("Match the following", "matching"), ("True or False", "true_false"), ("Fill in the blanks", "fill_blank")]:
            q = analyze_rules(pages("1. Example question", heading=heading)).questions[0]
            self.assertEqual(q.kind, kind)

    def test_question_type_is_independent_of_section_and_matching_has_two_columns(self):
        analysis = validate_analysis(analyze_rules(pages(
            "Section A",
            "1. Fill in the blanks:", "(i) Water freezes at ..... degrees.",
            "2. State whether True or False:", "(i) The Earth moves around the Sun.",
            "3. Match the following:", "Column A", "(i) Apple", "(ii) Carrot",
            "Column B", "(a) Fruit", "(b) Vegetable",
            "4. Explain photosynthesis.", "OR", "Describe respiration."
        )))
        self.assertEqual([q.kind for q in analysis.questions],
                         ["fill_blank", "true_false", "matching", "descriptive"])
        self.assertIn("OR\nDescribe respiration.", analysis.questions[3].english)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "question-types.xlsx"
            build_dynamic_excel(analysis, path)
            wb = load_workbook(path)
            self.assertEqual(sum("Fill Blanks" in name for name in wb.sheetnames), 1)
            self.assertEqual(sum("True-False" in name for name in wb.sheetnames), 1)
            matching = next(ws for ws in wb if "Matching" in ws.title)
            header_row = next(row[0].row for row in matching if row[0].value == "Q.No")
            headers = [cell.value for cell in matching[header_row]]
            self.assertIn("Column A (English)", headers)
            self.assertIn("Column B (English)", headers)
            self.assertFalse(any(str(value).startswith("Option ") for value in headers))
            row = [cell.value for cell in matching[header_row + 1]]
            self.assertIn("Apple", row[headers.index("Column A (English)")])
            self.assertIn("Fruit", row[headers.index("Column B (English)")])
            wb.close()

    def test_matching_pair_lines_are_split_without_a_section_template(self):
        analysis = analyze_rules(pages("37. Match the following:",
                                       "(i) Apple — Fruit", "(ii) Carrot — Vegetable"))
        self.assertEqual(analysis.questions[0].kind, "matching")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matching.xlsx"
            build_dynamic_excel(analysis, path)
            wb = load_workbook(path)
            ws = wb.worksheets[1]
            header_row = next(row[0].row for row in ws if row[0].value == "Q.No")
            headers = [cell.value for cell in ws[header_row]]
            values = [cell.value for cell in ws[header_row + 1]]
            self.assertIn("Carrot", values[headers.index("Column A (English)")])
            self.assertIn("Vegetable", values[headers.index("Column B (English)")])
            wb.close()

    def test_unnumbered_text_is_visible_for_review(self):
        analysis = validate_analysis(analyze_rules(pages("Explain photosynthesis without numbering.")))
        self.assertEqual(len(analysis.questions), 0)
        self.assertIn("photosynthesis", review_rows(analysis)[0][-1])

    def test_duplicate_numbers_not_silently_merged(self):
        analysis = validate_analysis(analyze_rules(pages("1. First task", "1. Different task")))
        self.assertEqual(len(analysis.questions), 2)
        self.assertTrue(any("Repeated" in r for r in analysis.questions[0].review))

    def test_ordered_html_list_numbers_preserved(self):
        analysis = analyze_rules(pages('<ol start="7"><li>First task</li><li>Second task</li></ol>'))
        self.assertEqual([q.number for q in analysis.questions], ["7", "8"])

    def test_symbols_and_mixed_scripts_preserved(self):
        q = analyze_rules(pages("1. पानी H2O का सूत्र? (A) 2 (B) 3")).questions[0]
        self.assertIn("H2O", q.text["हिंदी"])
        self.assertEqual(q.options[0].text["हिंदी"], "2")

    def test_numbered_blanks_and_or_do_not_create_sections(self):
        p = pages("Figures in the right hand margin indicate full marks.",
                  "7. विटामिन D का साधन ?", "(क) धूप (ख) हवा", "What supplies Vitamin D?", "(a) Sun (b) Air",
                  "8. रिक्त स्थानों को भरिए :", "Fill in the blanks :", "(i) पहला .....", "1", "First .....",
                  "(ii) दूसरा .....", "1", "Second .....", "9. कारण बताइए । 3", "Explain reasons.",
                  "13. पहला प्रश्न ? 7")
        p[0]['blocks'] += [{'label':'SectionHeader','html':'अथवा','reading_order':100},
                           {'label':'Text','html':'दूसरा प्रश्न ?','reading_order':101},
                           {'label':'Text','html':'First question?','reading_order':102},
                           {'label':'SectionHeader','html':'OR','reading_order':103},
                           {'label':'Text','html':'Alternative question?','reading_order':104},
                           {'label':'Text','html':'14. अगला प्रश्न ? 7','reading_order':105}]
        a = validate_analysis(analyze_rules(p))
        self.assertEqual([q.number for q in a.questions], ['7','8','9','13','14'])
        self.assertNotIn('Original', a.questions[0].text)
        blank = a.questions[1]
        self.assertEqual(blank.kind,'fill_blank')
        self.assertIn('(ii)',blank.text['हिंदी'])
        self.assertIn('Second .....',blank.english)
        self.assertEqual(blank.options,[])
        self.assertEqual(a.questions[2].kind,'descriptive')
        self.assertIn('अथवा',a.questions[3].text['हिंदी'])
        self.assertIn('OR\nAlternative question?',a.questions[3].english)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'grouped.xlsx'
            build_dynamic_excel(a,path)
            wb=load_workbook(path)
            self.assertEqual(len(wb.sheetnames),4)
            for ws in wb:
                self.assertTrue(all(selection.pane is None for selection in ws.sheet_view.selection))
                self.assertFalse(any('(Original)' in str(c.value) for row in ws for c in row))
            wb.close()

    def test_decimal_and_algebra_are_not_question_or_option_markers(self):
        result = analyze_rules(pages("1. Write the fraction.", "0.48 is a decimal.", "2. If (x+y) is positive explain why."))
        self.assertEqual([q.number for q in result.questions], ["1", "2"])
        self.assertIn("0.48", result.questions[0].english)
        self.assertEqual(result.questions[1].options, [])

    def test_ai_failure_falls_back_with_visible_note(self):
        class Failing:
            def extract(self, *args):
                raise TimeoutError("sensitive error must not be emitted")
        result = analyze_paper(pages("1. Test question"), "ai", Failing())
        self.assertEqual(result.method, "rules_fallback")
        self.assertEqual(len(result.questions), 1)
        self.assertNotIn("sensitive", result.notes[0])

    def test_ai_records_are_checked_against_source(self):
        class Fake:
            def extract(self, instruction, payload, schema):
                if schema is PaperPlan:
                    return PaperPlan()
                return Extraction(questions=[QuestionRecord(number="1", kind="short_answer", text={"English": "Invented text"},
                    marks=8, marks_evidence="8 marks", source_ids=["p1b1"])])
        result = validate_analysis(analyze_paper(pages("1. Actual text"), "ai", Fake()))
        self.assertEqual(result.method, "ai")
        self.assertIsNone(result.questions[0].marks)
        self.assertTrue(result.questions[0].review)

    def test_remote_requires_explicit_enablement(self):
        with patch.dict(os.environ, {"PAPER_AI_URL": "https://example.com/v1/chat/completions", "PAPER_AI_MODEL": "test", "PAPER_AI_ALLOW_REMOTE": "0"}):
            with self.assertRaises(ValueError):
                ModelClient()

    def test_local_model_transport_validates_schema(self):
        response = json.dumps({"choices": [{"message": {"content": '{"questions": []}'}}]}).encode()
        with patch.dict(os.environ, {"PAPER_AI_URL": "http://127.0.0.1:11434/v1/chat/completions", "PAPER_AI_MODEL": "test"}), patch("model_client.urlopen", return_value=io.BytesIO(response)) as request:
            result = ModelClient().extract("Extract", {"blocks": []}, Extraction)
        self.assertEqual(result.questions, [])
        body = json.loads(request.call_args.args[0].data)
        self.assertEqual(body["response_format"]["type"], "json_schema")

    def test_chunked_ai_failure_does_not_drop_later_pages(self):
        class FailingLater:
            calls = 0
            def extract(self, instruction, payload, schema):
                self.calls += 1
                if schema is PaperPlan:
                    return PaperPlan()
                if self.calls > 2:
                    raise ValueError("bad second chunk")
                return Extraction()
        p = pages("1. " + "First text " * 1000, "2. " + "Second text " * 1000)
        result = analyze_paper(p, "ai", FailingLater())
        self.assertEqual(result.method, "rules_fallback")
        self.assertEqual([q.number for q in result.questions], ["1", "2"])
        self.assertEqual(len(result.sources), 2)

    def test_excel_variable_columns_marks_and_formula_safety(self):
        analysis = validate_analysis(analyze_rules(pages("1. Select A. One B. Two C. Three", "2. =1+1", heading="Multiple Choice Questions")))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.xlsx"
            build_dynamic_excel(analysis, path)
            wb = load_workbook(path)
            ws = wb.worksheets[1]
            header_row = next(row[0].row for row in ws if row[0].value == "Q.No")
            headers = [c.value for c in ws[header_row]]
            self.assertIn("Option C (English)", headers)
            self.assertNotIn("Option D (English)", headers)
            self.assertIsNone(ws.cell(header_row + 1, headers.index("Marks") + 1).value)
            self.assertNotIn("Source blocks", headers)
            self.assertNotIn("Type", headers)
            self.assertEqual(ws.cell(header_row, 1).fill.fgColor.rgb, "001F4E78")
            self.assertTrue(ws.merged_cells.ranges)
            self.assertNotIn("Needs Review", wb.sheetnames)
            self.assertNotIn("Source OCR", wb.sheetnames)
            for sheet in wb:
                self.assertIsNone(sheet.sheet_view.pane)
                self.assertFalse(any(c.comment for row in sheet for c in row))
                self.assertFalse(any(c.data_type == "f" for row in sheet for c in row))
            wb.close()

    def test_large_source_preserved_in_analysis_not_workbook(self):
        original = "unclassified " * 4000
        analysis = analyze_rules(pages(original))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.xlsx"
            build_dynamic_excel(analysis, path)
            wb = load_workbook(path)
            self.assertNotIn("Source OCR", wb.sheetnames)
            recovered = json.loads(analysis.model_dump_json())["sources"][0]["text"]
            self.assertEqual(recovered, original.strip())
            wb.close()


if __name__ == "__main__":
    unittest.main()
