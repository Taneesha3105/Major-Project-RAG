import unittest

from app.ingestion.chunker import IngestionChunk
from app.ingestion.service import DocumentIngestionService


class IngestionStructureMetadataTests(unittest.TestCase):
    def test_build_structure_metadata_marks_table_like_content(self):
        metadata = DocumentIngestionService._build_structure_metadata(
            "Summary of Costs\nPrimary care visit $0 in-network.\nSpecialist visit $40 in-network."
        )

        self.assertTrue(metadata["table_like_row"])
        self.assertEqual(metadata["line_kind"], "table_like")
        self.assertGreaterEqual(len(metadata["sentence_offsets"]), 1)

    def test_build_structure_metadata_extracts_heading_anchor(self):
        metadata = DocumentIngestionService._build_structure_metadata(
            "Chapter 4 Benefits and Costs\nThis chapter explains covered services and cost sharing."
        )

        self.assertEqual(metadata["section_anchor"], "Chapter 4 Benefits and Costs")
        self.assertEqual(metadata["heading_path"], ["Chapter 4 Benefits and Costs"])

    def test_filter_low_information_parsed_chunks_drops_obvious_fragment_noise(self):
        chunks = [
            IngestionChunk(index=0, text="Team Handbook\nportal.example.com", start_char=0, end_char=30, metadata={}),
            IngestionChunk(
                index=1,
                text="Employees must submit expense reports within 30 days.",
                start_char=31,
                end_char=86,
                metadata={},
            ),
        ]

        filtered = DocumentIngestionService._filter_low_information_parsed_chunks(chunks)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].text, "Employees must submit expense reports within 30 days.")
        self.assertEqual(filtered[0].index, 0)

    def test_filter_low_information_parsed_chunks_keeps_short_but_useful_sentence(self):
        chunks = [
            IngestionChunk(index=0, text="Claims are paid within 30 days.", start_char=0, end_char=31, metadata={}),
        ]

        filtered = DocumentIngestionService._filter_low_information_parsed_chunks(chunks)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].text, "Claims are paid within 30 days.")


if __name__ == "__main__":
    unittest.main()
