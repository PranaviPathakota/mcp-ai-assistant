#!/usr/bin/env python3

import logging
from typing import Dict, List
import PyPDF2
import io

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extract text content from PDF files"""

    @staticmethod
    def extract_text_from_pdf(pdf_path: str) -> str:
        """
        Extract text content from a PDF file

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Extracted text content
        """
        try:
            text_content = []

            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)

                # Get total number of pages
                num_pages = len(pdf_reader.pages)
                logger.info(f"📄 Extracting text from {num_pages} pages...")

                # Extract text from each page
                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()

                    if text.strip():
                        # Add page separator
                        text_content.append(f"\n--- Page {page_num + 1} ---\n")
                        text_content.append(text)

                # Join all text
                full_text = "\n".join(text_content)

                logger.info(f"✅ Extracted {len(full_text)} characters from {num_pages} pages")

                return full_text

        except Exception as e:
            logger.error(f"❌ Error extracting text from PDF: {e}")
            return f"Error extracting text: {str(e)}"

    @staticmethod
    def extract_text_from_multiple_pdfs(pdf_paths: List[str]) -> Dict[str, str]:
        """
        Extract text from multiple PDF files

        Args:
            pdf_paths: List of PDF file paths

        Returns:
            Dictionary mapping filename to extracted text
        """
        results = {}

        for pdf_path in pdf_paths:
            try:
                import os
                filename = os.path.basename(pdf_path)

                logger.info(f"📄 Processing {filename}...")
                text = PDFExtractor.extract_text_from_pdf(pdf_path)

                if text and not text.startswith("Error"):
                    results[filename] = text
                else:
                    logger.error(f"❌ Failed to extract text from {filename}")

            except Exception as e:
                logger.error(f"❌ Error processing {pdf_path}: {e}")

        logger.info(f"✅ Successfully extracted text from {len(results)} PDFs")
        return results
