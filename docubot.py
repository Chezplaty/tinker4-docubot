"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob
import string
from collections import Counter

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "doing", "how", "what", "when", "where", "why",
    "which", "who", "whom", "this", "that", "these", "those",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "their", "of", "in", "on", "at", "to", "for", "with",
    "about", "as", "by", "from", "up", "down", "out", "over", "under",
    "again", "then", "once", "here", "there", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "can",
    "will", "just", "should", "now", "and", "or", "but", "if", "tell",
    "please",
}

class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.documents)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def _tokenize(self, text):
        """
        Split text into lowercase words, stripping surrounding punctuation.
        """
        words = []
        for word in text.lower().split():
            word = word.strip(string.punctuation)
            if word and word not in STOPWORDS:
                words.append(word)
        return words

    def build_index(self, documents):
        """
        TODO (Phase 1):
        Build a tiny inverted index mapping lowercase words to the documents
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md", "API_REFERENCE.md"],
            "database": ["DATABASE.md"]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}

        for filename, text in documents:
            for word in self._tokenize(text):
                if word not in index:
                    index[word] = set()
                index[word].add(filename)

        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """

        query_words = self._tokenize(query)
        text_word_counts = Counter(self._tokenize(text))
        score = 0
        for word in query_words:
            score += text_word_counts[word]

        return score

    def _extract_snippet(self, query, text, max_lines=5):
        """
        Return the lines of text most relevant to query, instead of the
        whole document. Each line is scored by how many query words it
        contains, and the top scoring lines are returned in their original
        order.
        """
        query_words = self._tokenize(query)

        scored_lines = []
        for line_num, line in enumerate(text.split("\n")):
            line_word_counts = Counter(self._tokenize(line))
            line_score = sum(line_word_counts[word] for word in query_words)
            if line_score > 0:
                scored_lines.append((line_score, line_num, line))

        if not scored_lines:
            return text.strip()

        scored_lines.sort(key=lambda item: item[0], reverse=True)
        top_lines = scored_lines[:max_lines]
        top_lines.sort(key=lambda item: item[1])

        return "\n".join(line for _, _, line in top_lines).strip()

    def retrieve(self, query, top_k=3):
        """
        TODO (Phase 1):
        Use the index and scoring function to select top_k relevant document snippets.

        Return a list of (filename, text) sorted by score descending.
        """
        query_words = self._tokenize(query)

        candidate_filenames = set()
        for word in query_words:
            candidate_filenames.update(self.index.get(word, ()))

        doc_lookup = dict(self.documents)

        scored = []
        for filename in candidate_filenames:
            text = doc_lookup[filename]
            score = self.score_document(query, text)
            if score > 0:
                snippet = self._extract_snippet(query, text)
                scored.append((score, filename, snippet))

        scored.sort(key=lambda item: item[0], reverse=True)

        results = [(filename, snippet) for _, filename, snippet in scored]
        return results[:top_k]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
