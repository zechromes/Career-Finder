"""Document validation behavior with synthetic PDF text and mocked OpenAI."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.profiles.extraction import extract_text_from_resume
from backend.schemas.resume import ResumeDocumentCheck
from backend.profiles.upload import validate_resume_document


class ResumeDetectionTests(unittest.TestCase):
    def setUp(self):
        self.page = MagicMock()
        self.page.images = []
        pdf = patch("backend.profiles.extraction.pdfplumber.open")
        self.addCleanup(pdf.stop)
        pdf.start().return_value.__enter__.return_value.pages = [self.page]
        client = patch("langchain_openai.ChatOpenAI")
        self.addCleanup(client.stop)
        self.client = client.start()
        self.classifier = self.client.return_value.with_structured_output.return_value

    def test_verified_resume_returns_original_text(self):
        for text in (
            "Alex Example\nEducation: BSc\nProjects: community website",
            "Alex Example\nCurriculum Vitae\nResearch and publications",
            "Alex Exemple\nFormation: licence\nCompétences: Python",
        ):
            with self.subTest(text=text):
                self.page.extract_text.return_value = text
                self.classifier.invoke.return_value = ResumeDocumentCheck(
                    document_type="resume"
                )
                self.assertIsNone(validate_resume_document(text))
                self.assertEqual(
                    self.classifier.invoke.call_args.args[0][-1], ("human", text)
                )

    def test_unrelated_and_uncertain_documents_have_distinct_errors(self):
        self.page.extract_text.return_value = "Invoice 123\nTotal $50"
        for verdict, message in (
            ("not_resume", "does not appear to be a resume/CV"),
            ("uncertain", "Please upload a clearer resume or CV PDF"),
        ):
            with self.subTest(verdict=verdict):
                self.classifier.invoke.return_value = ResumeDocumentCheck(
                    document_type=verdict
                )
                with self.assertRaisesRegex(ValueError, message):
                    validate_resume_document(self.page.extract_text.return_value)

    def test_provider_failure_is_not_a_non_resume_verdict(self):
        self.page.extract_text.return_value = "Synthetic document"
        self.classifier.invoke.side_effect = RuntimeError("private provider details")
        with self.assertRaisesRegex(ValueError, "could not verify") as raised:
            validate_resume_document(self.page.extract_text.return_value)
        self.assertNotIn("private provider details", str(raised.exception))

    def test_invalid_classification_does_not_pass(self):
        self.page.extract_text.return_value = "Synthetic document"
        for response in (None, {}, {"document_type": "unknown"}):
            with self.subTest(response=response):
                self.classifier.invoke.return_value = response
                with self.assertRaisesRegex(ValueError, "could not verify"):
                    validate_resume_document(self.page.extract_text.return_value)

    def test_empty_text_does_not_call_openai(self):
        self.page.extract_text.return_value = "  "
        self.assertEqual(extract_text_from_resume("synthetic.pdf"), "")
        self.client.assert_not_called()

    def test_scanned_document_extraction_does_not_call_openai(self):
        self.page.extract_text.return_value = ""
        self.page.images = [object()]
        self.classifier.invoke.return_value = ResumeDocumentCheck(
            document_type="not_resume"
        )
        with patch("shutil.which", return_value="/synthetic/tesseract"), patch(
            "subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="Invoice 123 Total $50"),
        ):
            self.assertEqual(
                extract_text_from_resume("synthetic.pdf"), "Invoice 123 Total $50"
            )
        self.client.assert_not_called()

    def test_plain_text_extraction_does_not_classify_documents(self):
        self.page.extract_text.return_value = "Invoice 123: Total $50"
        self.assertEqual(
            extract_text_from_resume("synthetic.pdf"), "Invoice 123: Total $50"
        )
        self.client.assert_not_called()

    def test_detection_model_can_be_configured_independently(self):
        self.classifier.invoke.return_value = ResumeDocumentCheck(
            document_type="resume"
        )
        with patch.dict(
            "os.environ", {"OPENAI_RESUME_CHECK_MODEL": "synthetic-check-model"}
        ):
            validate_resume_document("Synthetic resume")
        self.assertEqual(self.client.call_args.kwargs["model"], "synthetic-check-model")
