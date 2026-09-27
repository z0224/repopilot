"""Repository retrieval and code-indexing utilities."""

from .chunker import (
    CodeChunk,
    chunk_python_file,
    chunk_python_source,
)
from .hybrid import (
    HybridRetrievalResult,
    HybridRetriever,
)
from .indexer import (
    IndexBuildResult,
    RepositoryIndexer,
    index_repository,
)
from .lexical import (
    LexicalRetriever,
    RetrievalResult,
    search_chunks,
    tokenize,
)

from .semantic import (
    DEFAULT_MODEL,
    EmbeddingProvider,
    SemanticRetrievalResult,
    SemanticRetriever,
    SentenceTransformerEmbedder,
    chunk_embedding_text,
    cosine_similarity,
)

__all__ = [
    "CodeChunk",
    "HybridRetrievalResult",
    "HybridRetriever",
    "IndexBuildResult",
    "LexicalRetriever",
    "RepositoryIndexer",
    "RetrievalResult",
    "chunk_python_file",
    "chunk_python_source",
    "index_repository",
    "search_chunks",
    "tokenize",
    "RetrievalEvaluation",
    "aggregate_evaluations",
    "evaluate_hybrid_manifest",
    "evaluate_lexical_manifest",
    "evaluate_semantic_manifest",
    "evaluate_results",
    "unique_ranked_files",
    "DEFAULT_MODEL",
    "EmbeddingProvider",
    "SemanticRetrievalResult",
    "SemanticRetriever",
    "SentenceTransformerEmbedder",
    "chunk_embedding_text",
    "cosine_similarity",
]

from .evaluation import (
    RetrievalEvaluation,
    aggregate_evaluations,
    evaluate_hybrid_manifest,
    evaluate_lexical_manifest,
    evaluate_semantic_manifest,
    evaluate_results,
    unique_ranked_files,
)
