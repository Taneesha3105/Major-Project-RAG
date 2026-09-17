import unittest

from app.ingestion.chunker import split_parsed_document_into_chunks
from app.ingestion.parsers import ParsedBlock, ParsedDocument


class StructuredChunkingTests(unittest.TestCase):
    def test_structured_chunking_carries_heading_context_forward(self):
        parsed_document = ParsedDocument(
            source_format="pdf",
            parser_name="pdfplumber",
            normalized_text="",
            blocks=[
                ParsedBlock(kind="heading", text="Benefits and Costs", heading_path=["Benefits and Costs"], page_number=1),
                ParsedBlock(
                    kind="paragraph",
                    text=" ".join(["Primary care visits are covered."] * 12),
                    heading_path=["Benefits and Costs"],
                    page_number=1,
                ),
                ParsedBlock(
                    kind="paragraph",
                    text=" ".join(["Specialist visits may cost more."] * 10),
                    heading_path=["Benefits and Costs"],
                    page_number=1,
                ),
            ],
            parse_metadata={"parser_mode": "machine_text_no_ocr"},
        )

        chunks = split_parsed_document_into_chunks(parsed_document, chunk_size=180)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(chunk.text.startswith("Benefits and Costs") for chunk in chunks))

    def test_structured_chunking_keeps_table_rows_intact(self):
        primary_row = "Benefit: Primary care office visits | In-network: $0 copayment per visit | Out-of-network: $25 copayment per visit"
        specialist_row = "Benefit: Specialist office visits | In-network: $40 copayment per visit | Out-of-network: $70 copayment per visit"
        parsed_document = ParsedDocument(
            source_format="pdf",
            parser_name="pdfplumber",
            normalized_text="",
            blocks=[
                ParsedBlock(kind="heading", text="Your costs in 2026", heading_path=["Your costs in 2026"], page_number=1),
                ParsedBlock(
                    kind="table_row",
                    text=primary_row,
                    heading_path=["Your costs in 2026"],
                    page_number=1,
                    table_id="p1t1",
                    row_index=0,
                ),
                ParsedBlock(
                    kind="table_row",
                    text=specialist_row,
                    heading_path=["Your costs in 2026"],
                    page_number=1,
                    table_id="p1t1",
                    row_index=1,
                ),
            ],
            parse_metadata={"parser_mode": "machine_text_no_ocr"},
        )

        chunks = split_parsed_document_into_chunks(parsed_document, chunk_size=170)

        self.assertGreaterEqual(len(chunks), 1)
        combined_text = "\n".join(chunk.text for chunk in chunks)
        self.assertIn(primary_row, combined_text)
        self.assertIn(specialist_row, combined_text)
        self.assertTrue(all(chunk.metadata["table_like_row"] for chunk in chunks))
        self.assertEqual(chunks[0].metadata["page_start"], 1)
        self.assertEqual(chunks[0].metadata["heading_path"], ["Your costs in 2026"])

    def test_structured_chunking_merges_small_adjacent_narrative_chunks(self):
        parsed_document = ParsedDocument(
            source_format="pdf",
            parser_name="pdfplumber",
            normalized_text="",
            blocks=[
                ParsedBlock(kind="heading", text="Section 2.1 Eligibility requirements", heading_path=["Section 2.1 Eligibility requirements"], page_number=8),
                ParsedBlock(
                    kind="paragraph",
                    text="You are eligible for membership in our plan as long as you meet all these conditions:",
                    heading_path=["Section 2.1 Eligibility requirements"],
                    page_number=8,
                ),
                ParsedBlock(
                    kind="list_item",
                    text="- You have both Medicare Part A and Medicare Part B",
                    heading_path=["Section 2.1 Eligibility requirements"],
                    page_number=9,
                ),
                ParsedBlock(
                    kind="list_item",
                    text="- You live in our geographic service area and are lawfully present in the United States",
                    heading_path=["Section 2.1 Eligibility requirements"],
                    page_number=9,
                ),
            ],
            parse_metadata={"parser_mode": "machine_text_no_ocr"},
        )

        chunks = split_parsed_document_into_chunks(parsed_document, chunk_size=220)

        self.assertEqual(len(chunks), 1)
        self.assertIn("You are eligible for membership", chunks[0].text)
        self.assertIn("You have both Medicare Part A and Medicare Part B", chunks[0].text)
        self.assertIn("You live in our geographic service area", chunks[0].text)

    def test_structured_chunking_merges_short_table_like_fragment_with_same_section_chunk(self):
        parsed_document = ParsedDocument(
            source_format="pdf",
            parser_name="pdfplumber",
            normalized_text="",
            blocks=[
                ParsedBlock(
                    kind="heading",
                    text="Expense policy",
                    heading_path=["Expense policy"],
                    page_number=4,
                ),
                ParsedBlock(
                    kind="paragraph",
                    text="Foreign services are reimbursable only when the member submits the request directly.",
                    heading_path=["Expense policy"],
                    page_number=4,
                ),
                ParsedBlock(
                    kind="table_row",
                    text="Submission deadline | within 12 months",
                    heading_path=["Expense policy"],
                    page_number=4,
                    table_id="p4t1",
                    row_index=0,
                ),
            ],
            parse_metadata={"parser_mode": "machine_text_no_ocr"},
        )

        chunks = split_parsed_document_into_chunks(parsed_document, chunk_size=220)

        self.assertEqual(len(chunks), 1)
        self.assertIn("Foreign services are reimbursable", chunks[0].text)
        self.assertIn("Submission deadline | within 12 months", chunks[0].text)


if __name__ == "__main__":
    unittest.main()
