import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from surya_lan_server import JOBS, LOCK, PAGE, add_log, public_job, safe_pdf_name


class SuryaLanTests(unittest.TestCase):
    def test_ui_uses_mintbook_brand_and_short_labels(self):
        self.assertIn("<title>Mintbook OCR</title>", PAGE)
        self.assertIn("Create Word and Excel", PAGE)
        self.assertIn("Processing details", PAGE)
        self.assertNotIn("Surya OCR Studio", PAGE)

    def test_ui_supports_pdf_folder_and_output_directory(self):
        self.assertIn("webkitdirectory multiple", PAGE)
        self.assertIn("showDirectoryPicker", PAGE)
        self.assertIn("Process selected PDFs", PAGE)
        self.assertIn("saveOutput", PAGE)

    def test_analysis_stage_updates_job(self):
        with LOCK:
            JOBS["stage-test"] = {"log": "", "state": "ocr"}
        try:
            add_log("stage-test", "PIPELINE_STAGE: analyzing\n")
            self.assertEqual(JOBS["stage-test"]["state"], "analyzing")
            add_log("stage-test", "PIPELINE_STAGE: validating\n")
            self.assertEqual(JOBS["stage-test"]["state"], "validating")
        finally:
            with LOCK:
                JOBS.pop("stage-test", None)

    def test_filename_is_safe_and_pdf(self):
        self.assertEqual(safe_pdf_name(r"..\bad\science<script>.exe"), "science_script.pdf")

    def test_surya_progress_line_is_parsed(self):
        job_id = "progress-test"
        with LOCK:
            JOBS[job_id] = {"id":job_id,"filename":"x.pdf","state":"ocr","message":"","log":"","outputs":[],"created_at":0,"updated_at":0}
        add_log(job_id, "Page 24/56 [########------------]  42.9% | elapsed 03:10 | ETA 04:12 | split; saved (48.0s)\n")
        with LOCK:
            result = public_job(JOBS.pop(job_id))
        self.assertEqual(result["progress_current"], 24)
        self.assertEqual(result["progress_total"], 56)
        self.assertEqual(result["progress_percent"], 42.9)
        self.assertIn("split", result["page_status"])


if __name__ == "__main__": unittest.main()
