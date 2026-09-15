#!/usr/bin/env python3

import os
import logging
from typing import List, Dict, Optional
import google.generativeai as genai
from .extractor import PDFExtractor

logger = logging.getLogger(__name__)


class PDFQAHandler:
    """Handle PDF reading and Q&A using Gemini API for long documents"""

    def __init__(self, gemini_api_key: str):
        """
        Initialize PDF Q&A handler with Gemini API

        Args:
            gemini_api_key: Your Google Gemini API key
        """
        self.api_key = gemini_api_key
        genai.configure(api_key=self.api_key)

        # Use Gemini Pro for text (better for long documents)
        self.model = genai.GenerativeModel('gemini-3.6-flash')

        # Store loaded PDF contents
        self.pdf_contents: Dict[str, str] = {}

        logger.info("✅ PDF Q&A Handler initialized with Gemini API")

    def load_pdfs(self, pdf_paths: List[str]) -> Dict[str, str]:
        """
        Load multiple PDF files and extract text

        Args:
            pdf_paths: List of PDF file paths to load

        Returns:
            Dictionary mapping filename to extracted text content
        """
        logger.info(f"📚 Loading {len(pdf_paths)} PDF files...")

        # Expand home directory for all paths
        expanded_paths = []
        for path in pdf_paths:
            if path.startswith('~'):
                path = os.path.expanduser(path)
            expanded_paths.append(path)

        # Extract text from all PDFs
        loaded_pdfs = PDFExtractor.extract_text_from_multiple_pdfs(expanded_paths)

        # Store in instance variable
        self.pdf_contents = loaded_pdfs

        logger.info(f"✅ Successfully loaded {len(loaded_pdfs)} PDFs")
        return loaded_pdfs

    def prepare_context(self, max_length: int = 30000) -> str:
        """
        Prepare context from all loaded PDFs

        Args:
            max_length: Maximum character length for context (Gemini has large context window)

        Returns:
            Formatted context string
        """
        if not self.pdf_contents:
            return "No PDFs loaded."

        context_parts = []
        total_length = 0

        for filename, content in self.pdf_contents.items():
            # Add document separator
            doc_header = f"\n\n{'='*50}\nDocument: {filename}\n{'='*50}\n\n"

            # Check if we can fit this document
            if total_length + len(doc_header) + len(content) <= max_length:
                context_parts.append(doc_header + content)
                total_length += len(doc_header) + len(content)
            else:
                # Fit what we can
                remaining = max_length - total_length - len(doc_header)
                if remaining > 1000:  # Only add if meaningful content fits
                    context_parts.append(doc_header + content[:remaining] + "\n...[truncated]")
                break

        return "".join(context_parts)

    def answer_question(self, question: str, use_all_pdfs: bool = True) -> str:
        """
        Answer a question using Gemini API based on loaded PDFs

        Args:
            question: The question to answer
            use_all_pdfs: Whether to use all loaded PDFs or just summarize

        Returns:
            The answer from Gemini
        """
        if not self.pdf_contents:
            return "❌ No PDFs loaded. Please load PDFs first."

        try:
            # Prepare context from PDFs
            context = self.prepare_context(max_length=30000)  # Gemini has 32k token context

            # Create prompt
            prompt = f"""You are analyzing the following documents:

{context}

Based ONLY on the information in these documents, please answer this question:

{question}

Provide a clear, accurate answer. If the information is not in the documents, say so. When referencing information, mention which document it came from."""

            logger.info(f"💬 Asking Gemini: {question[:100]}...")

            # Generate response using Gemini
            response = self.model.generate_content(prompt)

            answer = "".join(part.text for part in response.parts if hasattr(part, "text")).strip()
            logger.info(f"✅ Received answer ({len(answer)} characters)")

            return answer

        except Exception as e:
            logger.error(f"❌ Error generating answer: {e}")
            return f"❌ Error: {str(e)}"

    def summarize_all_pdfs(self) -> str:
        """
        Generate a summary of all loaded PDFs

        Returns:
            Summary text
        """
        if not self.pdf_contents:
            return "❌ No PDFs loaded. Please load PDFs first."

        try:
            context = self.prepare_context(max_length=30000)

            prompt = f"""Please provide a comprehensive summary of the following documents:

{context}

For each document, provide:
1. Document name
2. Main topics covered
3. Key findings or points
4. Important details

Format the summary clearly with document names as headers."""

            logger.info("📝 Generating summary of all PDFs...")

            response = self.model.generate_content(prompt)
            summary = "".join(part.text for part in response.parts if hasattr(part, "text")).strip()

            logger.info("✅ Summary generated")
            return summary

        except Exception as e:
            logger.error(f"❌ Error generating summary: {e}")
            return f"❌ Error: {str(e)}"

    def list_loaded_pdfs(self) -> str:
        """Get a list of currently loaded PDFs"""
        if not self.pdf_contents:
            return "📚 No PDFs loaded."

        pdf_list = []
        for filename, content in self.pdf_contents.items():
            pdf_list.append(f"  • {filename} ({len(content):,} characters)")

        return f"📚 Loaded PDFs ({len(self.pdf_contents)}):\n" + "\n".join(pdf_list)

    def clear_pdfs(self):
        """Clear all loaded PDFs"""
        count = len(self.pdf_contents)
        self.pdf_contents.clear()
        logger.info(f"🗑️ Cleared {count} PDFs")
        return f"✅ Cleared {count} loaded PDFs"
